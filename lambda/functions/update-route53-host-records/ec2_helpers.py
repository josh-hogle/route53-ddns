# Python imports
import logging

# 3rd party imports

# local imports
from helpers import get_setting

# global variables
log = logging.getLogger()


def get_dhcp_options_domain(ec2_client, vpc_id):
    """Gets the DNS domain name associated with the DHCP Options Set associated with the given VPC ID.

    Parameters:
      ec2_client (object):  The EC2 client object.
      vpc_id (str):         The ID of the VPC to look up.

    Returns:
      str:  The DNS domain name associated with the DHCP Options Set on success or None on failure.
    """
    # get the DHCP options ID associated with this VPC
    vpcs = ec2_client.describe_vpcs(VpcIds=[vpc_id]).get("Vpcs", [])
    if len(vpcs) != 1:
        log.error(
            "describe_vpcs returned {} VPCs instead of expected 1".format(len(vpcs)))
        return None
    dhcp_options_id = vpcs[0].get("DhcpOptionsId", None)
    if dhcp_options_id is None:
        log.error("vpc is missing DhcpOptionsId")
        return None

    # get configuration for the DHCP Options Set associated with the VPC
    dhcp_options = ec2_client.describe_dhcp_options(
        DhcpOptionsIds=[dhcp_options_id]).get("DhcpOptions", [])
    if len(dhcp_options) != 1:
        log.error("describe_dhcp_options returned {} options instead of expected 1".format(
            len(dhcp_options)))
        return None
    dhcp_configs = dhcp_options[0].get("DhcpConfigurations", [])

    # find the 'domain-name' configuration setting and return its value
    for config in dhcp_configs:
        key = config.get("Key")
        if key == "domain-name":
            values = config.get("Values", [])
            if len(values) == 1:
                return values[0].get("Value", None)
    log.info("DHCP Options Set has no domain-name value set")
    return None


def get_dns_domain(ec2_client, vpc_id, region, tags):
    """Retrieves the DNS domain for the instance.

    DNS domain is determined as follows:
    - If the fn.aws.joshhogle.com/update-route53-host-records/dns_domain tag is defined, use its value.
    - Otherwise, retrieve the DHCP Options Set attached to the VPC and use the value of the domain-name field.  If this
      field does not exist or is not set, use REGION.compute.internal where REGION indicates the AWS region in which
      the instance resides.

    Parameters:
      ec2+c;oemt (object):  EC client object.
      vpc_id (str):         The ID of the VPC in which this instance is running.
      region (str):         The region in which this instance is running.
      tags (list):          A list of tags associated with the instance.

    Returns:
      str:  The DNS domain for the instance.
    """
    dns_domain_tag_name_account_tag = get_setting(
        "dns_domain_tag_name_account_tag")
    log.info("dns_domain_tag_name_account_tag: {}".format(
        dns_domain_tag_name_account_tag))
    default_dns_domain_tag_name = get_setting("default_dns_domain_tag_name")
    log.info("default_dns_domain_tag_name: {}".format(
        default_dns_domain_tag_name))

    dns_domain_tag = tags.get(
        dns_domain_tag_name_account_tag, default_dns_domain_tag_name)
    dns_domain = tags.get(dns_domain_tag, None)
    if dns_domain is not None:
        return dns_domain
    dns_domain = "{}.compute.internal".format(region)
    dhcp_options_domain = get_dhcp_options_domain(ec2_client, vpc_id)
    return dhcp_options_domain if dhcp_options_domain is not None else dns_domain


def get_hostname(tags):
    """Retrieves the hostname for the instance.

    Hostname is determined as follows:
    - If the fn.aws.joshhogle.com/update-route53-host-records/hostname tag is defined, use its value.
    - If the Name tag is defined, use its value.
    - If neither tag is defined, return None.  This will cause the script to abort in the main loop as there is no
      hostname to register in DNS.

    Parameters:
      tags (dict):  Dictionary of tags associated with the instance.

    Returns:
      str:  The hostname for the instance or None if no tags were found.
    """
    hostname_tag_name_account_tag = get_setting(
        "hostname_tag_name_account_tag")
    log.info("hostname_tag_name_account_tag: {}".format(
        hostname_tag_name_account_tag))
    default_hostname_tag_name = get_setting("default_hostname_tag_name")
    log.info("default_hostname_tag_name: {}".format(default_hostname_tag_name))

    hostname_tag = tags.get(hostname_tag_name_account_tag,
                            default_hostname_tag_name)
    hostname = tags.get(hostname_tag, None)
    if hostname is None:
        hostname = tags.get("Name", None)
    return hostname
