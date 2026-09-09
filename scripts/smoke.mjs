import { request } from 'node:http';
import assert from 'node:assert/strict';

// Exercise real dev-server proxies while avoiding OS-specific *.localhost DNS.
// Uses only the explicitly seeded local demo account. Never targets remote hosts.
const jar = new Map();
function call(port, host, path, { method='GET', body, authenticated=false, headers={} } = {}) {
  return new Promise((resolve,reject) => {
    const payload = body === undefined ? undefined : JSON.stringify(body);
    const req = request({hostname:'127.0.0.1', port, path, method, headers:{Host:`${host}:${port}`, ...(payload ? {'Content-Type':'application/json','Content-Length':Buffer.byteLength(payload)} : {}), ...(authenticated ? {Cookie:[...jar].map(([k,v])=>`${k}=${v}`).join('; ')} : {}), ...headers}}, response => {
      if (authenticated) for (const cookie of response.headers['set-cookie'] || []) { const [name,...value] = cookie.split(';')[0].split('='); jar.set(name,value.join('=')); }
      let text = '';
      response.on('data',chunk=>text+=chunk);
      response.on('end',()=>{ let data; try {data=JSON.parse(text);} catch {data=text;} resolve({status:response.statusCode,data,headers:response.headers}); });
    });
    req.setTimeout(10000,()=>req.destroy(new Error('Local server timed out. Start npm run dev:all.')));
    req.on('error',reject);
    req.end(payload);
  });
}
async function post(path,body={}) {
  const csrf = await call(4201,'admin.localhost','/api/auth/csrf/',{authenticated:true});
  assert.equal(csrf.status,200);
  return call(4201,'admin.localhost',path,{method:'POST',body,authenticated:true,headers:{'X-CSRFToken':csrf.data.token,Origin:'http://admin.localhost:4201'}});
}

let loggedIn = false;
try {
  for (const [port,host] of [[4200,'localhost'],[4201,'admin.localhost'],[4202,'platform.localhost'],[4203,'everyday-studio.localhost'],[4204,'payments.localhost']]) {
    assert.equal((await call(port,host,'/')).status,200,`${host} frontend`);
  }
  const login = await post('/api/auth/login/',{email:'owner@example.test',password:'Local-Mshoppa-2026!'});
  assert.equal(login.status,200,'Seed the local demo before running this test.');
  loggedIn = true;
  const businesses = await call(4201,'admin.localhost','/api/businesses/',{authenticated:true});
  assert.equal(businesses.status,200);
  assert.equal(businesses.data.results.some(b=>b.slug==='field-and-form'),false,'Second business must not leak');
  const business = businesses.data.results.find(b=>b.slug==='everyday-studio');
  assert.ok(business,'Demo business must exist');
  assert.equal(business.storefront_url,'http://everyday-studio.localhost:4203');
  assert.equal((await call(4203,'everyday-studio.localhost','/products/missing-smoke-product')).status,200,'Product route must load the Angular shell');
  assert.equal((await call(4203,'everyday-studio.localhost','/api/storefront/?product=missing-smoke-product')).status,404,'Missing products must not fall back to unrelated products');
  const link = await post(`/api/businesses/${business.id}/preview-link/`);
  assert.equal(link.status,200);
  const url = new URL(link.data.url), token = new URLSearchParams(url.hash.slice(1)).get('preview');
  const preview = await call(4203,url.hostname,'/api/storefront/preview/',{headers:{'X-Mshoppa-Preview':token}});
  assert.equal(preview.status,200,'Preview must work without an admin cookie');
  assert.equal(preview.data.name,'Everyday Studio');
  assert.equal(typeof preview.data.products_count,'number');
  assert.ok(Object.hasOwn(preview.data,'featured_product'));
  for (const key of ['logo_url','whatsapp_number','contact_address','instagram_url','return_refund_policy','privacy_policy','terms_conditions']) {
    assert.equal(typeof preview.data.settings[key],'string',`Footer field ${key}`);
  }
  const search = await call(4203,url.hostname,'/api/storefront/preview/?q=mshoppa-unmatched-smoke-6f198d',{headers:{'X-Mshoppa-Preview':token}});
  assert.equal(search.status,200);
  assert.equal(search.data.products_count,0);
  assert.deepEqual(search.data.products,[]);
  assert.equal(preview.headers['cache-control'],'private, no-store');
  assert.equal((await call(4203,'field-and-form.localhost','/api/storefront/preview/',{headers:{'X-Mshoppa-Preview':token}})).status,403);
  assert.equal((await call(4203,'unknown.localhost','/api/storefront/')).status,404);
  assert.equal((await call(4203,'everyday-studio.localhost','/api/storefront/')).status,business.published ? 200 : 404);
  console.log('PASS: five frontend hosts, proxied login/CSRF, business isolation, cookie-free host-bound preview, product search/featured response, public-store visibility, and unknown-store rejection.');
} finally {
  if (loggedIn) await post('/api/auth/logout/');
}
