'use strict';
const { test, afterEach }=require('node:test');
const assert=require('node:assert/strict');
const lead=require('../../api/lead.js');
const status=require('../../api/intake-status.js');
const {normalizedLead,submissionToken,parseBody}=lead.__test;
const envNames=['AIRTABLE_PERSONAL_ACCESS_TOKEN','TURNSTILE_SECRET_KEY','TURNSTILE_SITE_KEY','NORDBRIDGE_CRM_API_URL','NORDBRIDGE_CRM_API_TOKEN'];
const envOriginal=Object.fromEntries(envNames.map(k=>[k,process.env[k]]));
const origFetch=global.fetch;
afterEach(()=>{
  for(const k of envNames){if(envOriginal[k]===undefined)delete process.env[k];else process.env[k]=envOriginal[k];}
  global.fetch=origFetch;
});
function response(){
  return {statusCode:200, headers:{}, body:null, done:false,
    setHeader(k,v){this.headers[k]=v;},
    status(code){this.statusCode=code;return this;},
    json(body){this.body=body;this.done=true;return this;},
    send(body){this.body=body;this.done=true;return this;},
    end(){this.done=true;return this;}};
}
function sample(){
  return {_next:'https://nordbridge-global.com/thanks.html?submission=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
    'Company legal name':'Synthetic Bridge Works','Email':'Person@EXAMPLE.ORG',
    'Company country':'Denmark','_subject':'Business financing request',
    'Lead source page':'/business-financing.html',privacy_consent:'accepted',
    '_honey':'', 'cf-turnstile-response':'synthetic-turnstile-token'};
}
function request(data=sample()){return{method:'POST',headers:{origin:'https://nordbridge-global.com','content-type':'application/x-www-form-urlencoded'},body:data};}
function configured(){
  process.env.AIRTABLE_PERSONAL_ACCESS_TOKEN='synthetic-token';
  process.env.TURNSTILE_SECRET_KEY='synthetic-secret';
  process.env.TURNSTILE_SITE_KEY='1x00000000000000000000AA';
}
test('Normalizes all website financing fields without private financial documents',()=>{
  const lead=normalizedLead(sample());
  assert.equal(lead['Email'],'person@example.org');
  assert.equal(lead['Lead ID'],'WEB-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee');
  assert.equal(lead['Status'],'NEW');
  assert.equal(lead['Privacy Consent'],true);
  assert.equal(lead['Submitted At'].length>18,true);
  assert.equal('Available collateral' in lead,false);
});
test('All supported website form company aliases are recognized',()=>{
  for(const key of ['Company','Organization','Company name']){
    const data=sample();
    delete data['Company legal name'];
    data[key]='Test Organization';
    assert.equal(normalizedLead(data)['Company'],'Test Organization');
  }
});
test('Rejects URL replay from attacker controlled origin and missing consent',()=>{
  assert.equal(submissionToken({...sample(),_next:'https://evil.example/thanks.html?submission=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'}),'');
  assert.equal(normalizedLead({...sample(),privacy_consent:''}),null);
  assert.equal(normalizedLead({...sample(),Email:'fake@localhost'}),null);
  assert.equal(normalizedLead({...sample(),'Lead source page':'//evil.example/'}),null);
});
test('Accepts parsed form-urlencoded payload',()=>{
  const b=parseBody({headers:{'content-type':'application/x-www-form-urlencoded'},body:'Email=hello%40example.org&Company=Acme'});
  assert.deepEqual(b,{Email:'hello@example.org',Company:'Acme'});
});
test('Disabled while secrets are absent; no unprotected submission',async()=>{
  for(const k of envNames)delete process.env[k];
  const c=response();status({method:'GET'},c);
  assert.equal(c.body.ready,false);
  const r=response();await lead(request(),r);
  assert.equal(r.statusCode,503);
});
test('Rejects cross-origin write even if secrets configured',async()=>{
  configured();
  const r=response();await lead({...request(),headers:{...request().headers,origin:'https://evil.example'}},r);
  assert.equal(r.statusCode,403);
});
test('Valid challenge persists minimal lead exactly once and redirects to thank-you',async()=>{
  configured();
  const called=[];
  global.fetch=async (url,options)=>{
    called.push({url,options});
    if(url.includes('/siteverify'))return {ok:true,json:async()=>({success:true,hostname:'nordbridge-global.com'})};
    if(String(options?.method||'GET')==='POST')return{ok:true,json:async()=>({records:[{id:'recSynthetic'}]})};
    return{ok:true,json:async()=>({records:[]})};
  };
  const r=response();await lead(request(),r);
  assert.equal(r.statusCode,303);
  assert.match(r.headers.Location,/thanks\.html\?submission=aaaaaaaa/);
  assert.equal(called.length,3);
  assert.equal(JSON.parse(called[2].options.body).records[0].fields.Email,'person@example.org');
  assert.ok(!JSON.stringify(called[2].options.body).includes('synthetic-turnstile-token'));
});
test('Duplicate source submission ID creates no second CRM record',async()=>{
  configured();
  const called=[];
  global.fetch=async (url,options)=>{
    called.push({url,options});
    return{ok:true,json:async()=>url.includes('/siteverify')?{success:true,hostname:'nordbridge-global.com'}:{records:[{id:'recPrior'}]}};
  };
  const r=response();await lead(request(),r);
  assert.equal(r.statusCode,303);
  assert.equal(called.length,2);
});
test('Provider errors never create false conversion redirects',async()=>{
  configured();
  global.fetch=async (url)=>{
    if(url.includes('/siteverify'))return{ok:true,json:async()=>({success:true,hostname:'nordbridge-global.com'})};
    return{ok:false,status:403,json:async()=>({})};
  };
  const r=response();
  const old=console.error; console.error=()=>{};
  try {await lead(request(),r);}finally{console.error=old;}
  assert.equal(r.statusCode,503);
  assert.equal(r.headers.Location,undefined);
});
test('Turnstile hostname mismatch blocks request',async()=>{
  configured();
  global.fetch=async()=>({ok:true,json:async()=>({success:true,hostname:'other.example'})});
  const r=response();await lead(request(),r);
  assert.equal(r.statusCode,403);
});


test('Nested subscription-profile submit button still activates protected CRM route', async()=>{
  const fs=require('node:fs');
  const vm=require('node:vm');
  let wasInserted=false, challengeRendered=false;
  const wrapper={insertBefore(el,before){assert.equal(before,button);wasInserted=true;}};
  const button={parentNode:wrapper};
  const form={
    dataset:{},
    action:'https://formsubmit.co/fallback',
    method:'POST',
    addEventListener(type,handler,capture){assert.equal(type,'submit');assert.equal(capture,true);assert.equal(typeof handler,'function');},
    querySelector(sel){return sel==='button[type="submit"]'?button:null;}
  };
  const document={
    querySelectorAll(sel){return sel==='form.lead-form'?[form]:[];},
    createElement(){return{className:'',src:'',async:false,onload:null,remove(){}};},
    head:{appendChild(el){queueMicrotask(()=>el.onload());}}
  };
  const window={turnstile:{render(holder,opts){challengeRendered=true;assert.equal(opts['response-field-name'],'cf-turnstile-response');}}};
  const sandbox={document,window,fetch:async()=>({ok:true,json:async()=>({ready:true,sitekey:'1x00000000000000000000AA'})})};
  vm.runInNewContext(fs.readFileSync(require.resolve('../../forms-intake.js'),'utf8'),sandbox);
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(wasInserted,true);
  assert.equal(challengeRendered,true);
  assert.equal(form.action,'/api/lead');
  assert.equal(form.dataset.intakeEnabled,'true');
});

test('Server CRM rejects arbitrary remote URL',()=>{
  assert.equal(lead.__test.isApprovedCrmUrl('https://evil.example'),false);
  assert.equal(lead.__test.isApprovedCrmUrl('http://crm.nordbridge-global.com'),false);
  assert.equal(lead.__test.isApprovedCrmUrl('https://crm.nordbridge-global.com'),true);
});
test('Server CRM opt-in uses one protected write and no Airtable API',async()=>{
  configured();
  process.env.NORDBRIDGE_CRM_API_URL='https://crm.nordbridge-global.com';
  process.env.NORDBRIDGE_CRM_API_TOKEN='x'.repeat(40);
  const calls=[];
  global.fetch=async(url,options)=>{
    calls.push({url:String(url),options});
    if(String(url).includes('/siteverify'))return {ok:true,json:async()=>({success:true,hostname:'nordbridge-global.com'})};
    return {ok:true,json:async()=>({lead_id:'WEB-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',created:true})};
  };
  const r=response();await lead(request(),r);
  assert.equal(r.statusCode,303);
  assert.equal(calls.length,2);
  assert.ok(calls[1].url.endsWith('/v1/website-leads'));
  assert.equal(JSON.parse(calls[1].options.body).email,'person@example.org');
  assert.ok(!calls.some(x=>x.url.includes('airtable.com')));
  assert.equal(calls[1].options.headers.Authorization,'Bearer '+'x'.repeat(40));
});
test('Server selected but down => 503; no fallback to Airtable',async()=>{
  configured();
  process.env.NORDBRIDGE_CRM_API_URL='https://crm.nordbridge-global.com';
  process.env.NORDBRIDGE_CRM_API_TOKEN='x'.repeat(40);
  const calls=[];
  global.fetch=async(url)=>{
    calls.push(String(url));
    if(String(url).includes('/siteverify'))return {ok:true,json:async()=>({success:true,hostname:'nordbridge-global.com'})};
    return {ok:false,status:503,json:async()=>({})};
  };
  const r=response(), old=console.error; console.error=()=>{};
  try {await lead(request(),r);}finally {console.error=old;}
  assert.equal(r.statusCode,503);
  assert.equal(r.headers.Location,undefined);
  assert.equal(calls.length,2);
  assert.ok(!calls.some(url=>url.includes('airtable.com')));
});
