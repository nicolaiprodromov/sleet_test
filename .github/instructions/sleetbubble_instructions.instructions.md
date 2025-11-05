---
applyTo: '**'
---
We are working on sleetbubble which is a decentralized p2p radio streaming platform built on IPFS, docker, liquidsoap and python.
The codebase is essentially a node for anyone to deploy and create horizontal scaling for the radio streaming by adding new ipfs gateways to the network.

When working on the sleetbubble project, please keep the following guidelines in mind:

1. **Deployment**: Ensure that you are using the `deploy.sh` script from root to deploy the node for testing. When modifying anything related to deployment look at this file too.
2. **Code Style**: Dont write comments or make any documentation files or modify any documentation files. Very important.
3. **Environment**: The project uses docker so dont download libraries or dependencies directly to your local machine. Always be attentive to the docker setup and the dockerfiles.

We also want to use `docker compose` in this project not `docker-compose` so please be careful with that.

