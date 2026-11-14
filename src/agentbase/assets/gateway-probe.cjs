'use strict';
// First-party offline probe: only invalid model/routes; no provider requests.

const http = require('http'), net = require('net');
let bootstrap = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { bootstrap += chunk; });
process.stdin.on('end', async () => {
  const {capability} = JSON.parse(bootstrap);
  const checks = [];
  function check(command, passed) { checks.push({command, status:passed?'passed':'failed'}); }
  function call(method, path, body, token = capability) {
    return new Promise((resolve, reject) => {
      const bytes = Buffer.from(JSON.stringify(body || {}));
      const request = http.request({hostname:'gateway',port:8787,method,path,
        headers:{authorization:'Bearer '+token,'content-type':'application/json'}}, response => {
        let text=''; response.on('data',chunk=>text+=chunk);
        response.on('end',()=>resolve({status:response.statusCode,text}));
      });
      request.on('error',reject);
      request.end(method==='GET'?undefined:bytes);
    });
  }
  try {
    check('gateway reachable only through run capability',(await call('GET','/health')).status===200);
    check('unauthorized capability refused',(await call('GET','/health',null,'wrong')).status===401);
    check('foreign route refused',(await call('POST','/v1/files',{})).status===404);
    check('wrong model refused before API transport',(await call('POST','/v1/responses',{model:'unapproved',input:'fixture'})).status===422);
    const metrics=JSON.parse((await call('GET','/metrics')).text);
    check('no provider requests attempted',metrics.attempted_requests===0);
    check('no provider credential environment',!Object.keys(process.env).some(key=>/API_KEY|AUTH_TOKEN|CREDENTIAL|PROVIDER_SECRET/.test(key)));
    const blocked = await new Promise(resolve => {
      const socket=net.createConnection({host:'192.0.2.1',port:80});
      let ended=false;
      const done=value=>{if(!ended){ended=true;socket.destroy();resolve(value);}};
      socket.on('connect',()=>done(false));socket.on('error',()=>done(true));socket.setTimeout(300,()=>done(true));
    });
    check('worker external egress blocked',blocked);
    console.log(JSON.stringify({checks,provider_calls:metrics.attempted_requests}));
  } catch { console.log(JSON.stringify({error:'synthetic gateway smoke failed'})); process.exitCode=1; }
});
