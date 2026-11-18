// The gateway implements its mapping with real TCP sockets confined to loopback.
const assert = require('node:assert/strict');
const { createServer, connect } = require('node:net');
const { once } = require('node:events');
const execFile = require('node:util').promisify(
  require('node:child_process').execFile,
);
const { createRequire } = require('node:module');
const { join, resolve } = require('node:path');
const [checkout, portString] = process.argv.slice(2);
const platform = resolve(checkout),
  game = Number(portString),
  loopback = '127.0.0.1';
assert.ok(Number.isInteger(game) && game > 0 && game <= 65535);
delete process.env.HOMEPUTE_MAC_PORT_MAPPER;
require(
  createRequire(join(platform, 'packages/agent/package.json')).resolve(
    'tsx/cjs',
  ),
);
const { PublicIngressManager } = require(
  join(platform, 'packages/agent/src/public-ingress.ts'),
);
const { gameStatusDigest } = require(
  join(platform, 'packages/shared/src/minecraft-status.ts'),
);
async function listen(server, port) {
  server.listen(port, loopback);
  await once(server, 'listening');
}
async function close(server) {
  if (server.listening) await new Promise((resolve) => server.close(resolve));
}
async function main() {
  const reservation = createServer();
  await listen(reservation, 0);
  const outside = reservation.address().port;
  await close(reservation);
  const forward = createServer((client) => {
    const backend = connect(game, loopback);
    client.on('error', () => backend.destroy());
    backend.on('error', () => client.destroy());
    client.on('close', () => backend.destroy());
    backend.on('close', () => client.destroy());
    client.pipe(backend).pipe(client);
  });
  let ownerLabel,
    allowMapping = true;
  const service = 'urn:schemas-upnp-org:service:WANIPConnection:1';
  const fakeRouter = 'http://127.0.0.1/root.xml';
  const fetcher = async (input, options) => {
    if (String(input) === fakeRouter)
      return new Response(
        '<service><serviceType>' +
          service +
          '</serviceType><controlURL>/control</controlURL></service>',
      );
    assert.equal(String(input), 'http://127.0.0.1/control');
    const action = new Headers(options.headers)
      .get('soapaction')
      .split('#')[1]
      .replaceAll('"', '');
    const xml = String(options.body);
    if (action === 'GetExternalIPAddress')
      return new Response(
        '<NewExternalIPAddress>104.32.20.71</NewExternalIPAddress>',
      );
    assert.ok(
      xml.includes('<NewExternalPort>' + outside + '</NewExternalPort>') &&
        xml.includes('<NewProtocol>TCP</NewProtocol>'),
    );
    if (action === 'GetSpecificPortMappingEntry') {
      if (!ownerLabel)
        return new Response('<errorCode>714</errorCode>', { status: 500 });
      return new Response(
        '<NewInternalClient>192.168.20.10</NewInternalClient><NewInternalPort>' +
          game +
          '</NewInternalPort><NewPortMappingDescription>' +
          ownerLabel +
          '</NewPortMappingDescription>',
      );
    }
    if (action === 'AddPortMapping') {
      if (!allowMapping)
        return new Response('<errorCode>501</errorCode>', { status: 500 });
      assert.ok(
        xml.includes('<NewInternalPort>' + game + '</NewInternalPort>') &&
          xml.includes('<NewInternalClient>192.168.20.10</NewInternalClient>'),
      );
      ownerLabel = /<NewPortMappingDescription>([^<]+)</.exec(xml)[1];
      await listen(forward, outside);
      return new Response('<ok/>');
    }
    assert.equal(action, 'DeletePortMapping');
    ownerLabel = undefined;
    await close(forward);
    return new Response('<ok/>');
  };
  const manager = new PublicIngressManager({
    discover: async () => [fakeRouter],
    fetcher,
    localIp: () => '192.168.20.10',
  });
  const req = {
    deploymentId: 'local-terraria-fixture',
    portName: 'terraria',
    protocol: 'TCP',
    internalPort: game,
    externalPort: outside,
    description: 'Terraria fixture',
  };
  try {
    await assert.rejects(gameStatusDigest(loopback, outside, 'terraria'));
    assert.equal((await manager.ensureMapping(req)).status, 'mapped');
    await execFile(
      'python3',
      [join(__dirname, 'world_client.py'), String(outside)],
      { timeout: 12000 },
    );
    const local = await gameStatusDigest(loopback, game, 'terraria');
    assert.equal(await gameStatusDigest(loopback, outside, 'terraria'), local);
    await manager.releaseDeployment(req.deploymentId);
    await assert.rejects(gameStatusDigest(loopback, outside, 'terraria'));
    allowMapping = false;
    assert.equal((await manager.ensureMapping(req)).status, 'manual-required');
    await listen(forward, outside);
    assert.equal(await gameStatusDigest(loopback, outside, 'terraria'), local);
    console.log(
      'Verified disposable gateway add, readback, protocol through forward, removal, refusal and manually supplied forward.',
    );
  } finally {
    await manager.releaseDeployment(req.deploymentId);
    await close(forward);
  }
}
main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
