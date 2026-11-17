// 本地静态服务器：等价于 frontend/nginx.conf（SPA fallback + /api/ 去前缀代理）
const http=require('http'),fs=require('fs'),path=require('path');
const ROOT='/workspace/frontend',PORT=18240,API='http://127.0.0.1:19240';
const TYPES={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json'};
http.createServer((req,res)=>{
  if(req.url.startsWith('/api/')){
    const body=[];req.on('data',c=>body.push(c));req.on('end',()=>{
      const r=http.request(API+req.url.slice(4),{method:req.method,headers:req.headers},up=>{res.writeHead(up.statusCode,up.headers);up.pipe(res)});
      r.on('error',()=>res.writeHead(502).end('api unavailable'));if(body.length)r.write(Buffer.concat(body));r.end();
    });return;
  }
  let p=decodeURIComponent(req.url.split('?')[0]);if(p==='/')p='/index.html';
  let fp=path.join(ROOT,p);if(!fs.existsSync(fp)||fs.statSync(fp).isDirectory())fp=path.join(ROOT,'index.html');
  fs.readFile(fp,(e,d)=>{if(e)return res.writeHead(404).end();res.writeHead(200,{'Content-Type':TYPES[path.extname(fp)]||'application/octet-stream'});res.end(d)});
}).listen(PORT,()=>console.log('frontend on http://127.0.0.1:'+PORT));
