"""clean — (stretch) bulk terminate resources matching a tag.

WARNING — DESIGN-FOR-SAFETY
---------------------------
This is the most dangerous command in the CLI. Get the contract right:

  1. DEFAULT IS DRY-RUN. Without --apply the command MUST NOT touch resources.
     It only lists what WOULD be deleted.
  2. Even with --apply, you should consider printing a summary count first
     ("about to terminate N EC2 + M volumes — proceed?"), though for this
     starter a hard `--apply` flag is enough.
  3. Never use this with a tag you don't fully own. Reflection prompt in
     README covers the blast-radius scenario.

WHAT YOU MUST BUILD
-------------------
1. `_find_targets(tag_key, tag_val)` — return a dict like:
     {"ec2": [<instance ids in non-terminal state>],
      "volume": [<volume ids in 'available' state only>]}
   Skip terminated/shutting-down instances (already gone).
   Skip in-use volumes (can't delete while attached — would error anyway).

2. `run(args)` — call _find_targets, print the plan, then either:
     - bail with "(dry-run — pass --apply to ...)"  (default)
     - or actually terminate (when --apply)

HELPERS YOU CAN USE
-------------------
From commands._common:
  parse_kv(s) -> (k, v)

AWS APIS YOU'LL NEED
--------------------
- ec2.describe_instances() + describe_volumes() — same as list_cmd
- ec2.terminate_instances(InstanceIds=[...])
- ec2.delete_volume(VolumeId=...)  (per volume, no bulk API)

VERIFY
------
    pytest tests/test_clean.py -v
"""
import boto3

from commands._common import parse_kv


def _find_targets(tag_key, tag_val):
    """Return {"ec2": [...], "volume": [...]} matching tag in non-terminal state."""
    ec2 = boto3.client("ec2")
    targets = {"ec2": [], "volume": []}
    
    # Find EC2 instances
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate():
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                # Skip terminated/terminating instances
                state = instance["State"]["Name"]
                if state in ("terminated", "terminating", "stopped", "stopping"):
                    continue
                
                # Check tag match
                tags = {t["Key"]: t["Value"] for t in instance.get("Tags", [])}
                if tags.get(tag_key) == tag_val:
                    targets["ec2"].append(instance["InstanceId"])
    
    # Find EBS volumes
    paginator = ec2.get_paginator("describe_volumes")
    for page in paginator.paginate():
        for volume in page["Volumes"]:
            # Only include available volumes (not in-use)
            if volume["State"] != "available":
                continue
            
            # Check tag match
            tags = {t["Key"]: t["Value"] for t in volume.get("Tags", [])}
            if tags.get(tag_key) == tag_val:
                targets["volume"].append(volume["VolumeId"])
    
    return targets


def run(args):
    """Entry point.

    Args set by argparse:
        args.tag    — "key=value" string (REQUIRED)
        args.apply  — bool, must be True to actually delete (default False = dry-run)
    """
    tag_key, tag_val = parse_kv(args.tag)
    targets = _find_targets(tag_key, tag_val)
    
    # Check if anything to clean
    total = len(targets["ec2"]) + len(targets["volume"])
    if total == 0:
        print(f"Nothing to clean with tag {tag_key}={tag_val}")
        return
    
    # Print plan
    ec2_count = len(targets["ec2"])
    volume_count = len(targets["volume"])
    print(f"About to terminate: {ec2_count} EC2 instance(s), {volume_count} volume(s)")
    
    if targets["ec2"]:
        print(f"  EC2 instances: {', '.join(targets['ec2'])}")
    if targets["volume"]:
        print(f"  Volumes: {', '.join(targets['volume'])}")
    
    # Dry-run or apply
    if not args.apply:
        print("\n(dry-run — pass --apply to actually delete)")
        return
    
    # Actually delete
    ec2 = boto3.client("ec2")
    if targets["ec2"]:
        ec2.terminate_instances(InstanceIds=targets["ec2"])
        print(f"Terminated {ec2_count} EC2 instance(s)")
    
    if targets["volume"]:
        for vol_id in targets["volume"]:
            ec2.delete_volume(VolumeId=vol_id)
        print(f"Deleted {volume_count} volume(s)")
