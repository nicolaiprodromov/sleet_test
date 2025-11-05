#!/bin/bash

set -e

if [ -z "$1" ]; then
    echo "Usage: ./add-gateway.sh <new_node_gateway_url>"
    exit 1
fi

NEW_GATEWAY=$1

echo "Adding new gateway: ${NEW_GATEWAY}"

GATEWAYS_FILE="frontend/gateways.json"

if [ ! -f "${GATEWAYS_FILE}" ]; then
    echo '{"gateways": []}' > "${GATEWAYS_FILE}"
fi

TEMP_FILE=$(mktemp)
jq ".gateways += [\"${NEW_GATEWAY}\"] | .gateways |= unique" "${GATEWAYS_FILE}" > "${TEMP_FILE}"
mv "${TEMP_FILE}" "${GATEWAYS_FILE}"

echo "Gateway added to ${GATEWAYS_FILE}"

docker-compose exec nginx nginx -s reload

echo "Nginx reloaded. Gateway list updated!"
