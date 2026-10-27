// One production build, two isolated proxies. Each browser profile has its own
// backend/database/rate-limit state; production limits remain unchanged.
import { build, preview } from 'vite';

await build();
const servers=[];
for(const [port,api] of [[5174,8011],[5175,8012]]) {
  servers.push(await preview({preview:{host:'127.0.0.1',port,strictPort:true,
    proxy:{'/api':`http://127.0.0.1:${api}`}}}));
  console.log(`E2E frontend ready: http://127.0.0.1:${port}`);
}
for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>{
  for(const server of servers){server.httpServer.closeAllConnections?.();server.httpServer.close();}
  process.exit(0);
});
