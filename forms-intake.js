/* Enhanced private CRM intake is enabled only when server secrets and
 * Cloudflare Turnstile are provisioned. Otherwise FormSubmit remains in use.
 * Never embed Airtable API tokens or customer data in this public script.
 */
(function(){
  'use strict';
  const forms=Array.from(document.querySelectorAll('form.lead-form'));
  if(!forms.length)return;
  fetch('/api/intake-status',{credentials:'same-origin',cache:'no-store'})
    .then(res=>res.ok?res.json():{ready:false})
    .then(cfg=>{
      if(!cfg.ready||typeof cfg.sitekey!=='string'||!/^[A-Za-z0-9_-]{8,120}$/.test(cfg.sitekey))return;
      const script=document.createElement('script');
      script.src='https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
      script.async=true;
      script.onload=()=>{
        if(!window.turnstile||typeof window.turnstile.render!=='function')return;
        for(const form of forms){
          if(form.dataset.intakeEnabled==='true')continue;
          const button=form.querySelector('button[type="submit"]');
          if(!button)continue;
          const holder=document.createElement('div');
          holder.className='nb-turnstile';
          form.insertBefore(holder,button);
          try{
            window.turnstile.render(holder,{
              sitekey:cfg.sitekey,
              'response-field':true,
              'response-field-name':'cf-turnstile-response'
            });
            form.action='/api/lead';
            form.method='POST';
            form.dataset.intakeEnabled='true';
          }catch(e){holder.remove();} // original working FormSubmit unchanged
        }
      };
      script.onerror=()=>{}; // original working FormSubmit unchanged
      document.head.appendChild(script);
    })
    .catch(()=>{}); // Fallback remains the published form provider
})();
