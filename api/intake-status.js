'use strict';
const {isApprovedCrmUrl,stagingTestMode,productionTestKey}=require('./lead.js').__test;

// Only public readiness metadata. No tokens, private IDs or user records in response.
module.exports = (req, res) => {
  res.setHeader('Cache-Control', 'private, no-store, max-age=0');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  if (req.method !== 'GET') return res.status(405).json({ready:false});
  const key = (process.env.TURNSTILE_SITE_KEY || '').trim();
  const url = process.env.NORDBRIDGE_CRM_API_URL;
  const token = process.env.NORDBRIDGE_CRM_API_TOKEN;
  const serverMode = Boolean(url || token);
  const allowedHost = isApprovedCrmUrl(url);
  const providerReady = serverMode ? Boolean(allowedHost && token && token.length >= 32) :
    Boolean(process.env.AIRTABLE_PERSONAL_ACCESS_TOKEN);
  const ready = Boolean(!productionTestKey() && providerReady && process.env.TURNSTILE_SECRET_KEY &&
    /^[0-9A-Za-z_-]{8,120}$/.test(key));
  return res.status(200).json({ready, ...(ready ? {sitekey:key} : {}), ...(stagingTestMode() ? {testing:true} : {})});
};

