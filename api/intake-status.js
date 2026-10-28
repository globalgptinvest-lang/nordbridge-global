'use strict';
const {isApprovedCrmUrl,stagingTestMode,productionTestKey}=require('./lead.js').__test;

async function serverCrmHealthy(endpoint) {
  if (!isApprovedCrmUrl(endpoint)) return false;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch(new URL('/health', endpoint), {
      method: 'GET',
      headers: {Accept: 'application/json'},
      cache: 'no-store',
      signal: controller.signal
    });
    if (!response.ok) return false;
    const health = await response.json();
    return health && health.ready === true;
  } catch (_) {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'private, no-store, max-age=0');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  if (req.method !== 'GET') return res.status(405).json({ready:false});
  const key = (process.env.TURNSTILE_SITE_KEY || '').trim();
  const url = process.env.NORDBRIDGE_CRM_API_URL;
  const token = process.env.NORDBRIDGE_CRM_API_TOKEN;
  const serverMode = Boolean(url || token);
  const serverConfigured = Boolean(isApprovedCrmUrl(url) && typeof token === 'string' && token.length >= 32);
  const providerReady = serverMode
    ? Boolean(serverConfigured && await serverCrmHealthy(url))
    : Boolean(process.env.AIRTABLE_PERSONAL_ACCESS_TOKEN);
  const ready = Boolean(!productionTestKey() && providerReady && process.env.TURNSTILE_SECRET_KEY &&
    /^[0-9A-Za-z_-]{8,120}$/.test(key));
  return res.status(200).json({ready, ...(ready ? {sitekey:key} : {}), ...(stagingTestMode() ? {testing:true} : {})});
};

module.exports.__test={serverCrmHealthy};
