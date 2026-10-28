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
  "Support is tailored to the specific procurement and may include review of RFQ, RFP, ITB, EOI and prequalification documentation. The bidder remains responsible for its representations, pricing, technical solution and final submission.": ['uk', 'da', 'ar'],
  "Companies may approach NordBridge when evaluating opportunities published by organizations such as UNICEF, UNOPS, IOM and other international buyers. NordBridge is an independent service provider and is not affiliated with, endorsed by, or acting on behalf of these organizations.": ['uk', 'da', 'ar'],
  "Where permitted, support can be provided under a separately agreed fixed professional fee. Any success fee or introduction arrangement is documented separately in writing where applicable.": ['uk', 'da', 'ar'],
  "Check qualification criteria, experience, financial requirements, licenses and certifications before investing in a full bid.": ['uk', 'da', 'ar'],
  "Check mandatory requirements, missing documents and final submission readiness when the bid package is already being prepared.": ['uk', 'da', 'ar'],
  "Choose €250 Go / No-Go Review, €750 Compliance & Submission Review, or Full Tender Support from €1,250. Fixed-scope professional services require 100% advance payment before substantive work begins.": ['uk', 'da', 'ar'],
  "Payment: 100% advance payment in cleared funds before substantive fixed-scope work begins. Any success-fee or protected-introduction arrangement is separate and documented in writing where applicable.": ['uk', 'da', 'ar'],
  "Send the tender reference or link, deadline and the support you need. NordBridge can assess the scope before commercial terms are agreed.": ['uk', 'da', 'ar'],
  "Review scope and pricing before you proceed": ['uk', 'da', 'ar'],
  "Compare published support levels or send your requirement for a free initial fit review. Complex assignments are scoped and quoted in writing.": ['uk', 'da', 'ar'],
  "UN tender support and international institutional bid preparation": ['uk', 'da', 'ar'],
  "NordBridge Denmark provides independent tender-document, eligibility, compliance and bid-preparation support for companies pursuing UN and other institutional procurement opportunities. NordBridge is not affiliated with or endorsed by any UN organization and does not guarantee qualification or award.": ['uk', 'da', 'ar'],
  "Fixed-fee option": ['uk', 'da', 'ar'],
  "Tender Support Packages": ['uk', 'da', 'ar'],
  "Payment:": ['uk', 'da', 'ar'],
  "100% advance payment in cleared funds before substantive fixed-scope work begins. Any success-fee or protected-introduction arrangement is separate and documented in writing where applicable.": ['uk', 'da', 'ar'],
  "View Packages": ['uk', 'da', 'ar'],
  "Compare Tender Packages": ['uk', 'da', 'ar'],
  "Next step": ['uk', 'da', 'ar'],
  "NordBridge is an independent business introducer and tender-support provider. References to UN organizations describe procurement contexts only and do not imply affiliation, endorsement or representation. NordBridge does not guarantee tender awards.": ['uk', 'da', 'ar'],
  "Identify mandatory criteria, deadlines, forms, certifications, references and submission instructions.": ['uk', 'da', 'ar'],
  "Build a practical checklist and identify missing or inconsistent information before submission.": ['uk', 'da', 'ar'],
  "Review organization and completeness of the bidder's technical and commercial package.": ['uk', 'da', 'ar'],
  "Track clarification points, procurement milestones and final submission readiness.": ['uk', 'da', 'ar'],
  "International tender document support": ['uk', 'da', 'ar'],
  "UN Tender Support & Bid Preparation | NordBridge Denmark": ['uk', 'da', 'ar'],
  "Independent tender support for companies pursuing UN, UNICEF, UNOPS and other international procurement opportunities: requirements, eligibility, compliance and bid-document review.": ['uk', 'da', 'ar'],
  "UN Tender Support & Bid Preparation | NordBridge": ['uk', 'da', 'ar'],
  "Independent support for international procurement bids, including requirements, eligibility, compliance and document-readiness review.": ['uk', 'da', 'ar'],
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
