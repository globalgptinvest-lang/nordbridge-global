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
          // The submit button may be nested inside a paragraph or layout wrapper.
          // Insert alongside the actual button to preserve a working CRM route.
          button.parentNode.insertBefore(holder,button);
          try{
            window.turnstile.render(holder,{
              sitekey:cfg.sitekey,
              'response-field':true,
              'response-field-name':'cf-turnstile-response'
            });

            // Run before forms.js: never navigate to the intake endpoint with an
            // absent/expired challenge token or start a false submission event.
            form.addEventListener('submit',event=>{
              const token=form.querySelector('input[name="cf-turnstile-response"]');
              if(token&&typeof token.value==='string'&&token.value.trim())return;
              event.preventDefault();
              event.stopImmediatePropagation();
              let status=form.querySelector('.nb-intake-status');
              if(!status){
                status=document.createElement('div');
                status.className='nb-intake-status form-status error';
                status.setAttribute('role','alert');
                button.parentNode.insertBefore(status,button);
              }
              const language=document.documentElement.lang||'en';
              status.textContent=({
                en:'The security check is not complete. Please wait and try again, or email info@nordbridge-global.com.',
                uk:'Перевірку безпеки не завершено. Зачекайте та спробуйте ще раз або напишіть на info@nordbridge-global.com.',
                da:'Sikkerhedskontrollen er ikke afsluttet. Vent og prøv igen, eller skriv til info@nordbridge-global.com.',
                ar:'لم يكتمل فحص الأمان. يرجى الانتظار والمحاولة مجدداً أو مراسلة info@nordbridge-global.com.'
              })[language]||'Please complete the security check or email info@nordbridge-global.com.';
            },true);
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
