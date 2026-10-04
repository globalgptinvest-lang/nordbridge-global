(function(){
  function track(name,params){
    if(typeof window.gtag==='function') window.gtag('event',name,params||{});
  }
  document.addEventListener('click',function(e){
    var a=e.target.closest&&e.target.closest('a[href]');
    if(!a) return;
    var href=a.getAttribute('href')||'';
    var common={link_url:a.href||href,link_text:(a.textContent||'').trim().slice(0,100),page_path:location.pathname};
    if(href.indexOf('wa.me/')!==-1) track('whatsapp_click',common);
    else if(href.indexOf('mailto:')===0) track('email_click',common);
    else if(/(submit-tender|company-profile|buyer-request|contact)\.html/.test(href)) track('cta_click',Object.assign({cta_destination:href},common));
  });
})();