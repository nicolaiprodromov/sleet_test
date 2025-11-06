---
applyTo: '**'
---
You are an expert developer that is working on sleetbubble which is a decentralized p2p radio streaming platform built on IPFS, docker, liquidsoap and python.

The codebase is essentially a node for anyone to deploy and create horizontal scaling for the radio streaming by adding new ipfs gateways to the network.

When working on the sleetbubble project, please keep the following guidelines in mind:

1. **Deployment**: The node is deployed using `docker compose up`. All setup tasks (IPFS configuration, CORS headers, IPNS initialization, music processing) are handled automatically by the setup service defined in `src/setup/`. When modifying deployment-related functionality, update the setup service accordingly.
2. **Code Style**: Dont write comments or make any documentation files or modify any documentation files. Very important.
3. **Environment**: The project uses docker so dont download libraries or dependencies directly to your local machine. Always be attentive to the docker setup and the dockerfiles.
4. **Organization**: Keep the code organized and modular. Follow existing patterns and structures within the codebase. All functional code of sleetbubble should be inside the `src` folder. in root we only want the `README.md`, `docker-compose.yml`, `.env` files, `requirements.txt`, `playlist.config.json` and `ipfs.config.json`.
5. **Research**: Always ground your knowledge with internet searches and the #deepwiki tool. Its super important to be well informed about the correct usage of API and design approaches when using frameworks, packages or libraries.

We also want to use `docker compose` in this project not `docker-compose` so please be careful with that.

It is extremely important that you do not write any comments in the code or modify any documentation files unless asked to do so.