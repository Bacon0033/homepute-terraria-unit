# Homepute Terraria Server

Power the server from a node, choose the game version and start it. `LATEST` resolves Re-Logic’s current PC dedicated-server release at startup. Enter an exact version such as `1.4.4.9` to match an older client. The world and ban list live in the persistent `/config` volume. Back up a world before opening it with an older game version.

The release image targets Linux ARM64 and x86-64. Each image runs Re-Logic’s managed server with the native Mono package for its CPU, including Apple silicon, Intel Macs and Windows hosts using Linux containers. The Homepute engine selects the image for its own OS and CPU. The multi-platform release workflow tests each target on a native runner.

## Join

The game listens on TCP 7777 inside the unit. The configured host port can differ. Studio shows the LAN address for local players. Internet access defaults on and uses the same router mapping service as Minecraft. The node checks a Terraria protocol response from outside the network before displaying the verified public address. If the check fails, the forwarding field shows its status and offers a retry. Networks behind carrier-grade NAT can require a public address from the ISP. Only the game port requests internet forwarding.

## Server panel

Power the Terraria Server Panel from a node. Connect the server’s **Server channel OUT** to the panel’s **Server channel IN**, then choose **Open game panel** on the panel card in Studio. Studio authenticates the operator and checks the active wire for each command. The panel shows measured CPU and memory, recent game output, and the server version. The optional companion console key enables privileged access in the standalone LAN dashboard.

## Verify and release

Download Re-Logic’s 1.4.5.8 PC dedicated-server zip to `runtime/terraria-server.zip` and build the runtime image with Docker. The installer verifies the bundled archive digest. Run `python3 test/runtime-smoke.py IMAGE` to boot twice, join a disposable world, check its saved data and exercise authenticated commands. Pass a built Homepute checkout as a second argument to test the forwarding lifecycle with a software gateway.

The repository-root manifest identifies the published image. The release workflow validates the reviewed Playtest Room SDK evidence, builds both architectures and prepares a marketplace manifest from the immutable multi-platform digest and `release/manifest.template.json`.
