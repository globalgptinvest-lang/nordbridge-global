'use strict';
const { URL, URLSearchParams } = require('node:url');

const BASE = 'appydbFU5sRHKbxdV';
const LEADS = 'tbl4VQHyxvOw6usa9';
const ALLOWED_ORIGINS = new Set([
  'https://nordbridge-global.com',
  'https://www.nordbridge-global.com'
]);
const MAX_BYTES = 16000;
const VALID_EMAIL = /^[^@\s<>]{1,90}@[A-Za-z0-9][A-Za-z0-9.-]{1,240}\.[A-Za-z]{2,24}$/;

function clean(value, max=160) {
  if (typeof value !== 'string') return '';
  return value.replace(/[\u0000-\u001f\u007f]/g,' ').trim().slice(0,max);
}
function parseBody(req) {
  const type = String(req.headers['content-type'] || '').toLowerCase();
  let raw=req.body;
  if (type.includes('application/x-www-form-urlencoded')) {
    if(typeof raw==='string') raw=Object.fromEntries(new URLSearchParams(raw));
    else if(Buffer.isBuffer(raw)) raw=Object.fromEntries(new URLSearchParams(raw.toString('utf8')));
  } else if(type.includes('application/json')) {
    if(typeof raw==='string') raw=JSON.parse(raw);
  } else {throw new Error('bad_content_type');}
  if(!raw || Array.isArray(raw) || typeof raw!=='object') throw new Error('bad_body');
  if(Buffer.byteLength(JSON.stringify(raw))>MAX_BYTES) throw new Error('oversized');
  return raw;
}
function submissionToken(body) {
  const next=clean(body._next,700);
  try {
    const u=new URL(next);
    if(u.origin!=='https://nordbridge-global.com' || u.pathname!=='/thanks.html') return '';
    const token=u.searchParams.get('submission') || '';
    return /^[a-zA-Z0-9_-]{12,128}$/.test(token) ? token : '';
  } catch (_) {return '';}
}
function normalizedLead(body) {
  const email=clean(body.Email || body.email,255).toLowerCase();
  const company=clean(body['Company legal name'] || body.Company || body.Organization ||
    body['Company name'] || '',180);
  const consent=String(body.privacy_consent || '')==='accepted';
  const token=submissionToken(body);
  const kind=clean(body._subject || 'Website enquiry',100);
  const country=clean(body['Company country'] || body.Country || '',100);
  const source=clean(body['Lead source page'],250);
  if(!consent || !token || !VALID_EMAIL.test(email) || !company ||
      !source.startsWith('/') || source.startsWith('//')) return null;
  return {
    'Lead ID': 'WEB-'+token,
    'Company': company,
    'Email': email,
    'Country': country,
    'Source Form': kind,
    'Service': clean(body['Selected support package'] || body['Primary support needed'] ||
      body['Preferred financing type'] || body['Requirement type'] || kind,180),
    'Source Page': source,
    'Submitted At': new Date().toISOString(),
    'Privacy Consent': true,
    'Status': 'NEW',
    'Email Domain': email.split('@').pop()
  };
}
async function airtable(path, token, options={}) {
  const controller=new AbortController();
  const abort=setTimeout(()=>controller.abort(),8500);
  try {
    const r=await fetch('https://api.airtable.com/v0/'+BASE+'/'+LEADS+path,{
      ...options, signal:controller.signal,
      headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json',
        ...(options.headers||{})}
    });
    if(!r.ok) throw new Error('airtable_'+r.status);
    return await r.json();
  } finally {clearTimeout(abort);}
}

function isApprovedCrmUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' &&
      (/^(crm|office)\.nordbridge-global\.com$/.test(url.hostname) || url.hostname === 'crm.57.129.182.200.sslip.io') &&
      !url.port && (url.pathname === '/' || url.pathname === '') &&
      !url.username && !url.password && !url.search && !url.hash;
  } catch (_) {return false;}
}
async function serverCrm(fields, endpoint, token) {
  if (!isApprovedCrmUrl(endpoint) || typeof token !== 'string' || token.length < 32) {
    throw new Error('server_crm_not_ready');
  }
  const payload = {
    lead_id: fields['Lead ID'],
    company: fields.Company,
    email: fields.Email,
    country: fields.Country,
    source_form: fields['Source Form'],
    service: fields.Service,
    source_page: fields['Source Page'],
    privacy_consent: fields['Privacy Consent']
  };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8500);
  try {
    const response = await fetch(new URL('/v1/website-leads', endpoint), {
      method:'POST', signal:controller.signal,
      headers: {'Authorization':'Bearer '+token, 'Content-Type':'application/json'},
      body:JSON.stringify(payload)
    });
    if(!response.ok) throw new Error('server_crm_'+response.status);
    const receipt = await response.json();
    if(receipt.lead_id!==payload.lead_id) throw new Error('server_crm_bad_receipt');
    return receipt;
  } finally {clearTimeout(timer);}
}

function stagingTestMode() {
  return process.env.VERCEL_ENV==='preview' && process.env.NORDBRIDGE_INTAKE_TEST_MODE==='1' &&
    process.env.TURNSTILE_SECRET_KEY==='1x0000000000000000000000000000000AA' &&
    process.env.TURNSTILE_SITE_KEY==='1x00000000000000000000AA';
}
function allowedOrigin(origin) {
  if(ALLOWED_ORIGINS.has(origin))return true;
  return stagingTestMode() && /^[a-zA-Z0-9.-]+\.vercel\.app$/.test(process.env.VERCEL_URL||'') &&
    origin==='https://'+process.env.VERCEL_URL;
}
function productionTestKey() {
  return process.env.VERCEL_ENV==='production' &&
    (process.env.TURNSTILE_SECRET_KEY==='1x0000000000000000000000000000000AA' ||
     process.env.TURNSTILE_SITE_KEY==='1x00000000000000000000AA');
}
async function validateTurnstile(secret,response,ip) {
  if(!response || response.length>2500) return false;
  const params=new URLSearchParams({secret,response});
  if(ip && /^[a-fA-F0-9:.]{3,45}$/.test(ip)) params.set('remoteip',ip);
  const controller=new AbortController(), abort=setTimeout(()=>controller.abort(),8000);
  try {
    const result=await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify',{
      method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:params.toString(), signal:controller.signal
    });
    if(!result.ok) return false;
    const answer=await result.json();
    return answer.success===true && (['nordbridge-global.com','www.nordbridge-global.com'].includes(answer.hostname) ||
      (stagingTestMode() && response==='XXXX.DUMMY.TOKEN.XXXX'));
  } finally {clearTimeout(abort);}
}
function failure(res,status) {
  // The form does not redirect to success for failed validation/storage.
  res.setHeader('Cache-Control','no-store');
  return res.status(status).send(status===503?
    'Submission service temporarily unavailable. Please return to the form or email info@nordbridge-global.com.':
    'The submission could not be accepted. Please return to the form and check your details.');
}
async function handler(req,res) {
  res.setHeader('Cache-Control','no-store');
  if(req.method!=='POST') return res.status(405).send('Method not allowed');
  if(!allowedOrigin(String(req.headers.origin||''))) return failure(res,403);
  const token=process.env.AIRTABLE_PERSONAL_ACCESS_TOKEN, secret=process.env.TURNSTILE_SECRET_KEY;
  const crmUrl=process.env.NORDBRIDGE_CRM_API_URL, crmToken=process.env.NORDBRIDGE_CRM_API_TOKEN;
  const serverMode=Boolean(crmUrl || crmToken);
  if(productionTestKey() || !secret || !process.env.TURNSTILE_SITE_KEY ||
    (serverMode ? (!isApprovedCrmUrl(crmUrl) || !crmToken || crmToken.length<32) : !token)) return failure(res,503);
  if(Number(req.headers['content-length']||0)>MAX_BYTES) return failure(res,413);
  let body,fields;
  try {body=parseBody(req); fields=normalizedLead(body);}
  catch (_) {return failure(res,400);}
  if(!fields || clean(body._honey,100)) return failure(res,400);
  try {
    const challenge=clean(body['cf-turnstile-response'],2500);
    const ip=String(req.headers['x-forwarded-for']||'').split(',')[0].trim();
    if(!await validateTurnstile(secret,challenge,ip)) return failure(res,403);
    if(serverMode) {
      // Atomic duplicate suppression on VPS PostgreSQL by lead_id.
      // Never fall back to Airtable if the explicitly selected server is failing.
      await serverCrm(fields,crmUrl,crmToken);
    } else {
      // Legacy Airtable fallback remains until the staged VPS cutover succeeds.
      const formula='{Lead ID}="'+fields['Lead ID']+'"';
      const params=new URLSearchParams({maxRecords:'1',filterByFormula:formula});
      const existing=await airtable('?'+params.toString(),token);
      if(!existing.records?.length) {
        await airtable('',token,{method:'POST',body:JSON.stringify({records:[{fields}]})});
      }
    }
    const receiptSource = serverMode ? 'crm' : 'airtable';
    res.setHeader('Location',
      'https://www.nordbridge-global.com/thanks.html?submission='+encodeURIComponent(fields['Lead ID'].slice(4))+'&receipt='+receiptSource);
    return res.status(303).end();
  } catch (err) {
    // Avoid leaking provider responses or customer data into public logs.
    console.error('NordBridge lead intake temporarily failed:',String(err?.message||'unknown').slice(0,80));
    return failure(res,503);
  }
}
module.exports=handler;
module.exports.__test={parseBody,normalizedLead,submissionToken,clean,validateTurnstile,isApprovedCrmUrl,serverCrm,stagingTestMode,allowedOrigin,productionTestKey};

