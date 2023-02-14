# Python imports
import json
import logging
import logging.handlers
import os
import sys
sys.path.insert(0, "{}/package".format(os.environ.get("LAMBDA_TASK_ROOT", sys.path[0])))
sys.path.insert(0, "{}".format(os.environ.get("LAMBDA_TASK_ROOT", sys.path[0])))

# 3rd party imports
import boto3
import urllib.request

# local imports
from route53_helpers import register_host, unregister_host
from helpers import get_event_value, get_setting, tags_to_dict

# global variables
log = logging.getLogger()
org_client = boto3.client("organizations")
sts_client = boto3.client("sts")
dynamo_client = boto3.client("dynamodb")

def lambda_handler(event, context):
  """aws lambda main func"""
  log.setLevel(logging.INFO)
  log.info("=== Starting update-route53-host-records ===")
  log.info("sys.path: {}".format(sys.path))
  log.info("boto3 version: {}".format(boto3.__version__))

  # get settings from event
  account_id = get_event_value(event, "account")
  region = get_event_value(event, "region")
  details = get_event_value(event, "detail")
  instance_id = get_event_value(details, "instance-id")
  state = get_event_value(details, "state")

  # state must be "running" or "terminated" - otherwise there's nothing to do
  if state not in ["running", "shutting-down", "stopping"]:
    log.info("Nothing to do... state is '{}'".format(state))
    log.info("=== Finished update-route53-host-records ===\n")
    return 0
  log.info("state: {}".format(state))

  # configure settings
  account_state_tag = get_setting("account_state_tag")
  log.info("account_state_tag: {}".format(account_state_tag))
  account_enabled_values = [v.strip() for v in get_setting("account_enabled_values").split(":")]
  log.info("account_enabled_values: {}".format(account_enabled_values))
  iam_role_tag = get_setting("iam_role_tag")
  log.info("iam_role_tag: {}".format(iam_role_tag))
  default_iam_role = get_setting("default_iam_role")
  log.info("default_iam_role: {}".format(default_iam_role))

  # determine if the function is enabled on the account
  account = org_client.describe_account(AccountId=account_id)
  name = account.get("Name", account_id)
  tags = tags_to_dict(org_client.list_tags_for_resource(ResourceId=account_id).get("Tags", []))

  # skip the account if it is not enabled
  if account_state_tag not in tags or tags[account_state_tag] not in account_enabled_values:
    log.info("skipping disabled account: {} ({})".format(name, account_id))
    log.info("=== Finished update-route53-host-records ===\n")
    return 0
  log.info("updating records for account: {} ({})".format(name, account_id))

  # configure the IAM role
  iam_role = tags.get(iam_role_tag, None)
  if iam_role is None:
    iam_role = default_iam_role
  role_arn = "arn:aws:iam::{}:role/{}".format(id, iam_role)
  log.info("   arn: {}".format(role_arn))

  # assume the role
  role = sts_client.assume_role(RoleArn=role_arn, RoleSessionName="awsaccount_session")
  log.info("assumed role: {}".format(role_arn))

  # create the EC2 client
  ec2_client = boto3.client("ec2",
                            region_name=region,
                            aws_access_key_id=role["Credentials"]["AccessKeyId"],
                            aws_secret_access_key=role["Credentials"]["SecretAccessKey"],
                            aws_session_token=role["Credentials"]["SessionToken"])

  try:
    if state == "running":
      records = register_host(ec2_client, region, instance_id)
      table_name = get_setting("dynamo_table_name")
      dynamo_client.put_item(TableName=table_name, Item={
        "InstanceId": {
          "S": instance_id,
        },
        "Records": {
          "L": records,
        }
      })
    else:
      unregister_host(instance_id)
  finally:
    log.info("=== Finished update-route53-host-records ===\n")
  return 0


# invocation for debugging purposes
if __name__ == "__main__":
  if len(sys.argv) == 1:
    print("USAGE: {} <JSON event file>".format(sys.argv[0]))
    sys.exit(1)
  try:
    ch = logging.StreamHandler()
    log.addHandler(ch)
    with open(sys.argv[1], "r") as event_file:
      event = json.load(event_file)
    lambda_handler(event, None)
  except Exception as e:
    log.error(e)
