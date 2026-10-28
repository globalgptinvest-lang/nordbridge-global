const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../i18n.js'), 'utf8');
const start = source.indexOf('const translations=');
const end = source.indexOf('const original=new WeakMap();', start);
if (start < 0 || end < 0) throw new Error('Could not read the language dictionaries');
const dictionaries = new Function(source.slice(start, end) + '; return translations;')();

const checks = {
  'Choose the business problem you need to solve. NordBridge provides defined professional services, sourcing and introductions while final commercial decisions remain with the direct parties.': ['uk', 'da', 'ar'],
  'Procurement support for buyers, contractors and suppliers': ['uk', 'da', 'ar'],
  'NordBridge supports international B2B procurement with tender opportunity sourcing, bid-document coordination, compliance review, contractor and supplier search, and structured pre-contract introductions.': ['uk', 'da', 'ar'],
  'Identify procurement opportunities matched to your company capability, sector, geography and commercial range.': ['uk', 'da', 'ar'],
  'Independent eligibility, compliance and bid-document support for international institutional procurement.': ['uk', 'da', 'ar'],
  'Transparent pricing': ['uk', 'da', 'ar'],
  'Defined packages have clear starting prices. Complex or international mandates are quoted in writing according to scope.': ['uk', 'da', 'ar'],
  'Eligibility, key requirements, deadline, major compliance risks and high-level document gaps.': ['uk', 'da', 'ar'],
  'Human-curated monitoring matched to the company profile and verified opportunity alerts.': ['uk', 'da', 'ar'],
  'Upfront advisory pricing is shown on the funding-introduction page. Any success fee, if applicable, is agreed individually in writing for the specific mandate and jurisdiction. NordBridge is not a lender and does not guarantee funding.': ['uk', 'da', 'ar'],
  'Send the tender or your company profile for an initial fit review before choosing a paid scope.': ['uk', 'da', 'ar'],
  'NordBridge Denmark · CVR 46768736 · Hjørring, North Denmark · nordbridge-global.com · Independent tender support, procurement, supplier and contractor sourcing.': ['uk', 'da', 'ar'],
  'Denmark · CVR 46768736': ['uk', 'da', 'ar'],
  'International city representing global business connections': ['uk', 'da', 'ar'],
};

const failures = [];
for (const [english, languages] of Object.entries(checks)) {
  for (const language of languages) {
    const localized = dictionaries[language]?.[english];
    if (!localized || localized === english) failures.push(`${language}: ${english}`);
  }
}
if (failures.length) {
  console.error('Missing translations for services/pricing copy:\n' + failures.join('\n'));
  process.exitCode = 1;
} else {
  console.log(`Translation regression checks passed (${Object.keys(checks).length} strings × 3 languages)`);
}
