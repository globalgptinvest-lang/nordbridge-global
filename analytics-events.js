(function(){
  'use strict';
  var keys=['utm_source','utm_medium','utm_campaign','utm_content','utm_term'];
  var params=new URLSearchParams(location.search);
  function getStore(key){try{return sessionStorage.getItem('nb_'+key)||'';}catch(e){return '';}}
  function setStore(key,value){try{if(value)sessionStorage.setItem('nb_'+key,value);}catch(e){}}
  keys.forEach(function(key){var value=params.get(key);if(value)setStore(key,value);});
  if(params.get('deal_id'))setStore('deal_id',params.get('deal_id'));
  function attribution(){var out={};keys.forEach(function(k){out[k]=params.get(k)||getStore(k)||'';});out.deal_id=params.get('deal_id')||getStore('deal_id')||'';return out;}
  function track(name,extra){if(typeof window.gtag!=='function')return;var a=attribution();var data={page_path:location.pathname,lead_source:a.utm_source||'direct',lead_medium:a.utm_medium||'(none)',lead_campaign:a.utm_campaign||'(not set)'};if(a.utm_content)data.utm_content=a.utm_content;if(a.utm_term)data.utm_term=a.utm_term;if(a.deal_id)data.deal_id=a.deal_id;Object.keys(extra||{}).forEach(function(k){data[k]=extra[k];});window.gtag('event',name,data);}
  function decorate(url){try{var u=new URL(url,location.href);if(u.origin!==location.origin)return url;var a=attribution();keys.concat(['deal_id']).forEach(function(k){if(a[k]&&!u.searchParams.has(k))u.searchParams.set(k,a[k]);});return u.pathname+u.search+u.hash;}catch(e){return url;}}
  document.addEventListener('click',function(e){var link=e.target.closest&&e.target.closest('a[href]');if(!link)return;var href=link.getAttribute('href')||'';var common={link_url:link.href||href,link_text:(link.textContent||'').trim().slice(0,100)};if(href.indexOf('wa.me/')!==-1||href.indexOf('whatsapp.com/')!==-1)track('whatsapp_click',common);else if(href.indexOf('mailto:')===0)track('email_click',common);else if(/^(?!https?:\/\/|#|tel:|javascript:)/i.test(href)||href.indexOf(location.origin)===0){var decorated=decorate(link.href||href);if(decorated!==href)link.setAttribute('href',decorated);if(/(submit-tender|company-profile|buyer-request|contact|business-financing|free-tender-fit-check)\.html/.test(href))track('cta_click',Object.assign({cta_destination:href},common));}},true);
  document.addEventListener('DOMContentLoaded',function(){document.querySelectorAll('a[href]').forEach(function(link){var href=link.getAttribute('href')||'';if(/^(?!https?:\/\/|#|mailto:|tel:|javascript:)/i.test(href)||href.indexOf(location.origin)===0){var d=decorate(link.href||href);if(d!==href)link.setAttribute('href',d);}});track('nb_landing_view',{landing_page:location.pathname,referrer:document.referrer||'direct'});});
  window.NordBridgeTracking={track:track,attribution:attribution,decorate:decorate};
})();