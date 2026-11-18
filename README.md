# Homepute Terraria Server

The marketplace manifest at the repository root identifies the published version. The candidate in `release/manifest.template.json` runs the 1.4.5.8 dedicated server. Its runtime image requires an immutable registry digest after acceptance.

## Host a world

Select the world size and name before the first start. The unit stores the world in the persistent `/config` volume. Stopping sends the server its save-and-exit command. The node publishes your chosen host TCP port to the game’s internal port 7777. Friends on the same network can use the LAN address shown in Studio.

Enable **Internet access** to ask the node to map the game port. After a manual router change, use **Retry port forwarding**. A compatible node and Website observer check for a Terraria protocol response from outside the LAN. If verification fails, forward the displayed TCP port to the node’s current LAN address in the router. To confirm the intended world, join it from a different network. The console and dashboard use separate LAN ports.

## Manage the server

The Studio console delivers a command for the selected deployment. To use the companion dashboard, set a companion key of at least 16 characters, connect the server channel to the dashboard and enter the same key there. The public channel view contains bounded world state. Reading logs or sending a console command through it requires the key.

## Verify a local build

Download the 1.4.5.8 dedicated server archive from Re-Logic into `runtime/terraria-server.zip`. The build verifies its SHA-256. Run `python3 test/runtime-smoke.py IMAGE` with the resulting local image and an available SD Engine. The fixture boots the game twice, uses random loopback ports, opens a current-version client session, reads the world name and checks command access, and compares the saved world across boots. It removes its disposable world afterward. Pass a built Homepute checkout as a second argument to test the node’s port-mapping lifecycle against a software gateway. The gateway opens and closes a real loopback forward through which a client reads that same world and tests a manually supplied rule after it declines automatic mapping.

Publishing is manual. The release workflow reads a reviewed commit from the private Playtest Room repository and runs its 2,090-case gate before registry login. Configure the protected environment’s `HOMEPUTE_SDK_EVIDENCE_COMMIT` and read-only `HOMEPUTE_SDK_EVIDENCE_READ_TOKEN` when releasing.
