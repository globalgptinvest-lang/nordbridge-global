(function(){
  'use strict';

  var STORAGE_KEY='nb_google_consent_v1';

  window.dataLayer=window.dataLayer||[];
  window.gtag=window.gtag||function(){window.dataLayer.push(arguments);};

  function readChoice(){
    try{return localStorage.getItem(STORAGE_KEY)||'';}catch(e){return '';}
  }

  function consentState(choice){
    var granted=choice==='granted';
    return {
      ad_storage:granted?'granted':'denied',
      analytics_storage:granted?'granted':'denied',
      ad_user_data:granted?'granted':'denied',
      ad_personalization:granted?'granted':'denied'
    };
  }

  var initialChoice=readChoice();
  var initialState=consentState(initialChoice);
  initialState.wait_for_update=500;
  window.gtag('consent','default',initialState);

  function saveChoice(choice){
    try{localStorage.setItem(STORAGE_KEY,choice);}catch(e){}
    window.gtag('consent','update',consentState(choice));
    var banner=document.getElementById('nb-consent-banner');
    if(banner)banner.hidden=true;
  }

  function showBanner(){
    var banner=document.getElementById('nb-consent-banner');
    if(banner)banner.hidden=false;
  }

  function buildUi(){
    if(document.getElementById('nb-consent-banner'))return;

    var banner=document.createElement('div');
    banner.id='nb-consent-banner';
    banner.setAttribute('role','dialog');
    banner.setAttribute('aria-label','Privacy choices');
    banner.style.cssText='position:fixed;left:16px;right:16px;bottom:16px;z-index:99999;max-width:920px;margin:auto;background:#fff;color:#142033;border:1px solid #d8dee8;border-radius:12px;box-shadow:0 10px 35px rgba(0,0,0,.18);padding:16px;font:14px/1.45 Arial,sans-serif';
    banner.innerHTML='<div style="font-weight:700;margin-bottom:6px">Privacy choices</div>'+
      '<div>NordBridge uses Google Analytics and Google Ads measurement to understand website use and confirmed business enquiries. If you accept, cookies/personal data may also be used for advertising measurement and ads personalization. We do not intentionally send form contents such as names, email addresses, phone numbers or tender documents to Google Analytics. <a href="privacy.html" style="color:#0b57d0">Privacy Notice</a> · <a href="https://business.safety.google/privacy/" target="_blank" rel="noopener" style="color:#0b57d0">How Google uses business data</a>.</div>'+
      '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:12px">'+
      '<button type="button" id="nb-consent-reject" style="border:1px solid #9aa5b1;background:#fff;color:#142033;border-radius:8px;padding:9px 14px;cursor:pointer">Reject non-essential</button>'+
      '<button type="button" id="nb-consent-accept" style="border:1px solid #142033;background:#142033;color:#fff;border-radius:8px;padding:9px 14px;cursor:pointer">Accept</button>'+
      '</div>';

    document.body.appendChild(banner);
    document.getElementById('nb-consent-accept').addEventListener('click',function(){saveChoice('granted');});
    document.getElementById('nb-consent-reject').addEventListener('click',function(){saveChoice('denied');});

    var settings=document.createElement('button');
    settings.type='button';
    settings.id='nb-consent-settings';
    settings.textContent='Privacy choices';
    settings.style.cssText='position:fixed;left:12px;bottom:12px;z-index:99998;border:1px solid #c7ced8;background:#fff;color:#334155;border-radius:18px;padding:6px 10px;font:12px Arial,sans-serif;cursor:pointer;box-shadow:0 3px 12px rgba(0,0,0,.12)';
    settings.addEventListener('click',showBanner);
    document.body.appendChild(settings);

    if(readChoice())banner.hidden=true;
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',buildUi);
  else buildUi();
})();