'use strict';

// Only public readiness metadata. No tokens, private IDs or user records in response.
module.exports = (req, res) => {
  res.setHeader('Cache-Control', 'private, no-store, max-age=0');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  if (req.method !== 'GET') return res.status(405).json({ready:false});
  const key = (process.env.TURNSTILE_SITE_KEY || '').trim();
  const ready = Boolean(process.env.AIRTABLE_PERSONAL_ACCESS_TOKEN &&
    process.env.TURNSTILE_SECRET_KEY && /^[0-9A-Za-z_-]{8,120}$/.test(key));
  return res.status(200).json({ready, ...(ready ? {sitekey:key} : {})});
};
