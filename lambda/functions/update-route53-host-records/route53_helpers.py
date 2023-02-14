# Python imports
import logging

# 3rd party imports
import boto3

# local imports
from ec2_helpers import get_dhcp_options_domain, get_dns_domain, get_hostname
from helpers import get_setting, tags_to_dict

# global variables
log = logging.getLogger()
route53_client = boto3.client("route53")

def get_aliases(route53_client, vpc_id, region, tags, aliases_tag, alias_type, default_dns_domain):
  """Retrieves settings for additional records for an instance.

  Parameters:
    route53_client (object):  Route53 client object.
    vpc_id (str):             The ID of the VPC in which the instance is running.
    region (str):             The region in which the instance is running.
    tags (dict):              Instance tags.
    aliases_tag (str):        Base path to the aliases tag for the instance.
    alias_type (str):         Type of alias: public or private.
    default_dns_domain (str): The default DNS domain to use for non-FQDN.
  
  Returns:
    dict: Dictionary containing aliases as keys and hostname, dns_domain, fqdn, and zone_id as the items.
  """
  aliases = tags.get("{}/{}".format(aliases_tag, alias_type), [])
  settings = {}
  for alias in [v.strip() for v in aliases.split(",")]:
    log.info("retrieving settings for '{}' alias".format(alias))
    tag_base = "{}/{}/{}".format(aliases_tag, alias_type, alias)

    # if a hostname is defined for the alias, use it; otherwise use the alias as the hostname
    hostname = tags.get("{}/hostname".format(tag_base), None)
    if hostname is None:
      log.warn("   no hostname found for {} alias '{}' - using alias as hostname".format(alias_type, alias))
      hostname = alias

    # if the hostname is not an FQDN , append the default DNS domain to it
    parts = hostname.split(".")
    if len(parts) == 1:
      dns_domain = default_dns_domain
      fqdn = "{}.{}".format(hostname, dns_domain)
    else:
      hostname = parts[0]
      dns_domain = ".".join(parts[1:])
      fqdn = hostname
    log.info("   hostname: {}".format(hostname))
    log.info("   dns_domain: {}".format(dns_domain))
    log.info("   fqdn: {}".format(fqdn))

    # get a zone ID if one is associated with it
    zone_id = tags.get("{}/zone_id".format(tag_base), None)
    if zone_id is None:
      if alias_type == "private":
        zone_id = get_private_zone_id(route53_client, vpc_id, region, dns_domain)
      elif alias_type == "public":
        zone_id = get_public_zone_id(route53_client, dns_domain)
    log.info("   zone_id: {}".format(zone_id))

    settings[alias] = {"hostname": hostname, "dns_domain": dns_domain, "fqdn": fqdn, "zone_id": zone_id}
  return settings


def get_public_zone_id(route53, zone_name):
  """Attempts to retrieve the Route53 Zone ID associated with the given zone name.

  If no exact match to the given zone name is found, this function will check for a matching parent domain up to
  the root domain.

  Parameters:
    route53 (object): The Route53 client object.
    zone_name (str):  The name of the public zone to lookup.
  
  Returns:
    str:  The ID of the Route53 zone if found or None on error or if it is not found.
  """
  if zone_name is None or zone_name == "":
    return None
  hosted_zones = route53.list_hosted_zones().get("HostedZones", [])
  zone_parts = zone_name.split(".")
  while len(zone_parts) >= 2:
    check_zone = "{}.".format(".".join(zone_parts))
    log.info("searching for matching zone: {}".format(check_zone))
    for zone in hosted_zones:
      config = zone.get("Config", {})
      if not config.get("PrivateZone", False) and zone.get("Name", None) == check_zone:
        return zone.get("Id", None)
    zone_parts.pop(0)
  return None


def get_private_zone_id(route53_client, vpc_id, region, zone_name):
  """Attempts to retrieve the Route53 Zone ID associated with the given zone name attached to the given VPC.

  If no exact match to the given zone name is found, this function will check for a matching parent domain up to
  the root domain.

  Parameters:
    route53_client (object):  The Route53 client object.
    vpc_id (str):             The VPC ID with which the zone should be associated.
    region (str):             The AWS region in which the instance is running.
    zone_name (str):          The name of the public zone to lookup.
  
  Returns:
    str:  The ID of the Route53 zone if found or None on error or if it is not found.
  """
  if zone_name is None or zone_name == "":
    return None
  if zone_name == "{}.compute.internal":
    log.info("default private zone in use - skipping zone ID lookup")
    return None
  hosted_zones = route53_client.list_hosted_zones().get("HostedZones", [])
  zone_parts = zone_name.split(".")
  while len(zone_parts) >= 2:
    check_zone = "{}.".format(".".join(zone_parts))
    log.info("searching for matching zone: {}".format(check_zone))
    for zone in hosted_zones:
      config = zone.get("Config", {})
      if config.get("PrivateZone", False) and zone.get("Name", None) == check_zone:
        zone_id = zone.get("Id", None)
        log.info("found matching zone ID: {} -- verifying VPC attachment".format(zone_id))
        # Make sure this zone is associated with the given VPC ID
        zone_vpcs = route53_client.get_hosted_zone(Id=zone.get("Id", None)).get("VPCs", [])
        for vpc in zone_vpcs:
          if vpc.get("VPCId", None) == vpc_id:
            log.info("zone is attached to VPC")
            return zone.get("Id", None)
        log.info("zone is not attached to VPC")
    zone_parts.pop(0)
  return None


def register_host(ec2_client, region, instance_id):
  """Handles registration of host records in Route53.

  Parameters:
    ec2_client (object):  EC2 client object.
    region (str):         The region in which the client is located.
    instance_id (str):    The ID of the instance being registered.

  Returns:
    list: List of records that were registered with Route53.

  Raises:
    Exception:  If an error occurs.
  """
  records = []

  # get instance metadata
  log.info("--- instance metadata ---")
  reservations = ec2_client.describe_instances(InstanceIds=[instance_id]).get("Reservations", [])
  if len(reservations) != 1:
    msg = "unexpected result when retrieving instance data: {}".format(reservations)
    log.fatal(msg)
    raise Exception(msg)
  instances = reservations[0].get("Instances", [])
  if len(instances) != 1:
    msg = "unexpected result when retrieving instance data: {}".format(reservations)
    log.fatal(msg)
    raise Exception(msg)
  instance = instances[0]
  public_ip = instance.get("PublicIpAddress", "")
  if public_ip is "":
    log.info("host does not have a public IP")
    public_ip = None
  else:
    log.info("public_ip: {}".format(public_ip))
  private_ip = instance.get("PrivateIpAddress", "")
  if private_ip == "":
    msg = "instance is missing private IP: {}".format(reservations)
    log.fatal(msg)
    raise Exception(msg)
  log.info("private_ip: {}".format(private_ip))
  vpc_id = instance.get("VpcId", "")
  if vpc_id == "":
    msg = "instance is missing VPC ID: {}".format(reservations)
    log.fatal(msg)
    raise Exception(msg)
  log.info("vpc_id: {}".format(vpc_id))

  # get FQDN and PTR address
  instance_tags = tags_to_dict(instance.get("Tags", []))
  hostname = get_hostname(instance_tags)
  if hostname is None:
    log.warn("no hostname is defined for the instance - skipping registration")
    return records
  parts = hostname.split(".")
  if len(parts) == 1:
    dns_domain = get_dns_domain(ec2_client, vpc_id, region, instance_tags)
    fqdn = "{}.{}".format(hostname, dns_domain)
  else:
    hostname = parts[0]
    dns_domain = ".".join(parts[1:])
    fqdn = hostname
  log.info("hostname: {}".format(hostname))
  log.info("dns_domain: {}".format(dns_domain))
  log.info("fqdn: {}".format(fqdn))
  octets = private_ip.split(".")
  ptr_record = "{}.{}.{}.{}.in-addr.arpa".format(octets[3], octets[2], octets[1], octets[0])
  log.info("ptr_record: {}".format(ptr_record))
  arpa_zone = "{}.{}.{}.in-addr.arpa".format(octets[2], octets[1], octets[0])
  log.info("arpa_zone: {}".format(arpa_zone))

  # update A record for private zone
  log.info("--- private record registration ---")
  private_zone_id = get_private_zone_id(route53_client, vpc_id, region, dns_domain)
  if private_zone_id is None:
    log.info("no matching private zone for DNS domain attached to VPC - skipping A record registration")
  else:
    log.info("private_zone_id:{}".format(private_zone_id))
    records.append({
      "zone_id": private_zone_id,
      "type": "A",
      "name": fqdn,
      "data": private_ip
    })
    change_record("UPSERT", route53_client, private_zone_id, "A", fqdn, private_ip)

  # configure aliases tags
  aliases_tag_name_account_tag = get_setting("aliases_tag_name_account_tag")
  log.info("aliases_tag_name_account_tag: {}".format(aliases_tag_name_account_tag))
  default_aliases_tag_name = get_setting("default_aliases_tag_name")
  log.info("default_aliases_tag_name: {}".format(default_aliases_tag_name))
  aliases_tag = instance_tags.get(aliases_tag_name_account_tag, default_aliases_tag_name)

  # update private aliases
  log.info("--- private alias registration ---")
  aliases = get_aliases(route53_client, vpc_id, region, instance_tags, aliases_tag, "private", dns_domain)
  for alias, settings in aliases.items():
    log.info("updating private alias: {}".format(alias))
    if settings["zone_id"] is None:
      log.info("   no matching Route53 ZoneID was found - skipping A record registration")
      continue
    records.append({
      "zone_id": settings["zone_id"],
      "type": "A",
      "name": settings["fqdn"],
      "data": private_ip
    })
    change_record("UPSERT", route53_client, settings["zone_id"], "A", settings["fqdn"], private_ip)

  # update PTR record for private ARPA zone
  log.info("--- ARPA record registration ---")
  arpa_zone_id = get_private_zone_id(route53_client, vpc_id, region, arpa_zone)
  if arpa_zone_id is None:
    log.info("   no matching private APRA zone attached to VPC - skipping PTR record registration")
  else:
    log.info("   arpa_zone_id: {}".format(arpa_zone_id))
    records.append({
      "zone_id": arpa_zone_id,
      "type": "PTR",
      "name": ptr_record,
      "data": fqdn + "."
    })
    change_record("UPSERT", route53_client, arpa_zone_id, "PTR", ptr_record, fqdn + ".")

  # if host has no public IP we are finished
  if public_ip is None:
    return 0

  # update public aliases
  log.info("--- public alias registration ---")
  aliases = get_aliases(route53_client, vpc_id, region, instance_tags, aliases_tag, "public", dns_domain)
  for alias, settings in aliases.items():
    log.info("updating public alias: {}".format(alias))
    if settings["zone_id"] is None:
      log.info("   no matching Route53 ZoneID was found - skipping A record registration")
      continue
    records.append({
      "zone_id": settings["zone_id"],
      "type": "A",
      "name": settings["fqdn"],
      "data": public_ip
    })
    change_record("UPSERT", route53_client, settings["zone_id"], "A", settings["fqdn"], public_ip)
  return 0


def unregister_host(instance_id):
  pass


def change_record(action, route53_client, zone_id, record_type, record_name, record_data):
  """Creates a change_resource_record_sets request in Route53 for the given DNS record.

  Parameters:
    action (str):             The type of the change action to perform.
    route53_client (object):  Route53 client object.
    zone_id (str):            The zone ID in which to create or remove the record.
    record_type (str):        The type of record to create or delete.
    record_name (str):        The name of the record to create or delete.
    record_data (str):        The actual data for the record (eg: hostname or IP).
  """
  try:
    route53_client.change_resource_record_sets(HostedZoneId=zone_id,
                                               ChangeBatch={
                                                   "Changes": [{
                                                       "Action": action,
                                                       "ResourceRecordSet": {
                                                           "Name": record_name + ".",
                                                           "Type": record_type,
                                                           "TTL": 300,
                                                           "ResourceRecords": [{
                                                               "Value": record_data
                                                           }]
                                                       }
                                                   }]
                                               })
    log.info("{} successful for {} record: {} -> {}".format(action, record_type, record_name, record_data))
  except Exception as e:
    log.error("{} failed for {} record '{}' -> '{}': {}".format(action, record_type, record_name, record_data, e))
