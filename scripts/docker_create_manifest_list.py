#!/usr/bin/env python3

# This takes the REGISTRY_IMAGE env ( echo "REGISTRY_IMAGE=ghcr.io/${GITHUB_REPOSITORY,,}" >>${GITHUB_ENV} as the first argument - a string indicateing the image name in the registry
# and the DOCKER_METADATA_OUTPUT_JSON env ( output of docker/metadata-action ) as the second argument - a JSON string containing tags
# and creates a docker manifest list using docker buildx imagetools create

import json
import os
import sys
import subprocess

REGISTRY_IMAGE = sys.argv[1]
DOCKER_METADATA_OUTPUT_JSON = sys.argv[2]

print(f"Registry image: '{REGISTRY_IMAGE}'", file=sys.stderr)
print(f"Docker metadata output JSON: '{DOCKER_METADATA_OUTPUT_JSON}'", file=sys.stderr)


try:
    docker_meta = json.loads(DOCKER_METADATA_OUTPUT_JSON)
except json.JSONDecodeError as e:
    print(f"Error decoding JSON: {e}")
    sys.exit(1)

tags = []

for tag in docker_meta.get("tags", []):
    tags.append("-t")
    tags.append(tag)

print(f"Tags for manifest list: {tags}", file=sys.stderr)

DIGESTS = [
    f"{REGISTRY_IMAGE}@sha256:{digest}"
    for digest in [filename for filename in os.listdir(".") if os.path.isfile(filename)]
]

print(f"Digests: {DIGESTS}", file=sys.stderr)

command = ["docker", "--debug", "buildx", "imagetools", "create", *tags, *DIGESTS]

print(f"Command: {command}", file=sys.stderr)
try:
    result = subprocess.run(command)
except subprocess.CalledProcessError as e:
    print(f"CalledProcessError running docker buildx imagetools create: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Exception running docker buildx imagetools create: {e}")
    sys.exit(1)
