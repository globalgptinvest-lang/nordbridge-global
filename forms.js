const nbParams=new URLSearchParams(location.search);
const nbDealId=nbParams.get('deal_id')||('NB-'+new Date().toISOString().slice(0,10).replaceAll('-','')+'-'+Math.random().toString(36).slice(2,8).toUpperCase());
const nbAttributionKeys=['utm_source','utm_medium','utm_campaign','utm_content','utm_term'];
const nbAttribution={};
nbAttributionKeys.forEach(key=>{const value=nbParams.get(key);if(value){nbAttribution[key]=value;try{sessionStorage.setItem('nb_'+key,value);}catch(err){}}else{try{const stored=sessionStorage.getItem('nb_'+key);if(stored)nbAttribution[key]=stored;}catch(err){}}});
if(nbParams.get('deal_id')){try{sessionStorage.setItem('nb_deal_id',nbParams.get('deal_id'));}catch(err){}}
const nbStoredDealId=(()=>{try{return sessionStorage.getItem('nb_deal_id')||nbDealId;}catch(err){return nbDealId;}})();
document.querySelectorAll('.lead-form').forEach(form=>{
  form.action='https://formsubmit.co/b725f79abde568a9761c73d482dca435';
  form.method='POST';

  const packageSelect=form.querySelector('select[name="Selected support package"]');
  if(packageSelect){
    const requested=nbParams.get('package');
    const packageMap={'250':'€250 — Tender Go / No-Go Review','750':'€750 — Compliance & Submission Review','1250':'From €1,250 — Full Tender Support','custom':'Custom scope / Other support'};
    if(requested&&packageMap[requested]&&[...packageSelect.options].some(o=>o.textContent.trim()===packageMap[requested])) packageSelect.value=packageMap[requested];
  }

  const estimate=nbParams.get('estimate');
  const services=nbParams.get('services');
  const priority=nbParams.get('priority');
  const addHidden=(name,value)=>{let input=form.querySelector('input[name="'+name+'"]');if(!input){input=document.createElement('input');input.type='hidden';input.name=name;form.appendChild(input);}input.value=value;return input;};

  addHidden('_subject',form.dataset.mailSubject||'NordBridge website enquiry');
  addHidden('NordBridge Deal ID',nbStoredDealId);
  addHidden('Lead source page',location.pathname);
  addHidden('Lead referrer',document.referrer||'direct');
  nbAttributionKeys.forEach(key=>{if(nbAttribution[key]) addHidden(key.toUpperCase(),nbAttribution[key]);});
  if(estimate) addHidden('Calculator estimate',estimate);
  if(services) addHidden('Calculator services',services);
  if(priority) addHidden('Calculator priority',priority);
  addHidden('_template','table');
  addHidden('_next','https://nordbridge-global.com/thanks.html');
  addHidden('_url',location.href);

  if(!form.querySelector('input[name="_honey"]')){const honey=document.createElement('input');honey.type='text';honey.name='_honey';honey.autocomplete='off';honey.tabIndex=-1;honey.className='form-honey';honey.setAttribute('aria-hidden','true');form.appendChild(honey);}
  if(!form.querySelector('.privacy-consent')){const consent=document.createElement('label');consent.className='privacy-consent';consent.innerHTML='<span><input type="checkbox" name="privacy_consent" value="accepted" required> I agree that NordBridge may use the information submitted here to review and respond to this business enquiry. <a href="privacy.html" target="_blank" rel="noopener">Privacy Notice</a>.</span>';const btn=form.querySelector('button[type="submit"]');form.insertBefore(consent,btn);}

  form.addEventListener('submit',e=>{
    if(!form.reportValidity()){e.preventDefault();return;}
    if(form.dataset.submitting==='true'){e.preventDefault();return;}

    // Diagnostic only: this records an attempted valid form submission.
    // It is deliberately NOT the lead conversion event.
    if(typeof window.gtag==='function') window.gtag('event','nb_form_submit_attempt',{
      form_subject:form.dataset.mailSubject||'NordBridge website enquiry',
      page_path:location.pathname,
      deal_id:nbStoredDealId,
      lead_source:nbAttribution.utm_source||'direct',
      lead_medium:nbAttribution.utm_medium||'(none)',
      lead_campaign:nbAttribution.utm_campaign||'(not set)'
    });

    // A success redirect must return this one-time, per-submission token.
    // An ordinary visit to thanks.html must never become a lead conversion.
    const confirmationToken=(window.crypto&&typeof window.crypto.randomUUID==='function')?window.crypto.randomUUID():String(Date.now())+'-'+Math.random().toString(36).slice(2);
    addHidden('_next','https://nordbridge-global.com/thanks.html?submission='+encodeURIComponent(confirmationToken));
    try{
      sessionStorage.setItem('nb_pending_enquiry','1');
      sessionStorage.setItem('nb_pending_enquiry_ts',String(Date.now()));
      sessionStorage.setItem('nb_pending_deal_id',nbStoredDealId);
      sessionStorage.setItem('nb_pending_enquiry_token',confirmationToken);
    }catch(err){}

    form.dataset.submitting='true';
    const email=form.querySelector('input[type="email"]');if(email&&email.value) addHidden('_replyto',email.value);
    addHidden('_url',location.href);
    const btn=form.querySelector('button[type="submit"]');
    if(btn){if(!btn.dataset.originalText) btn.dataset.originalText=btn.textContent;const lang=document.documentElement.lang||'en';const sending={en:'Sending…',uk:'Надсилання…',da:'Sender…',ar:'جارٍ الإرسال…'}[lang]||'Sending…';btn.disabled=true;btn.setAttribute('aria-disabled','true');btn.textContent=sending;}
    const status=document.createElement('div');status.className='form-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');status.textContent=({en:'Submitting your enquiry…',uk:'Надсилаємо вашу заявку…',da:'Sender din forespørgsel…',ar:'جارٍ إرسال طلبك…'}[document.documentElement.lang||'en']||'Submitting your enquiry…');form.appendChild(status);
    window.setTimeout(()=>{if(document.visibilityState==='visible'&&form.dataset.submitting==='true'){resetSubmission();status.className='form-status error';status.textContent=({en:'The page did not confirm submission. Please try again or contact NordBridge directly.',uk:'Сторінка не підтвердила надсилання. Спробуйте ще раз або зв’яжіться з NordBridge напряму.',da:'Siden bekræftede ikke indsendelsen. Prøv igen, eller kontakt NordBridge direkte.',ar:'لم تؤكد الصفحة إرسال الطلب. يرجى المحاولة مجدداً أو التواصل مع NordBridge مباشرة.'}[document.documentElement.lang||'en']||'The page did not confirm submission. Please try again or contact NordBridge directly.');}},12000);
  });
  function resetSubmission(){
    form.dataset.submitting='false';
    try{['nb_pending_enquiry','nb_pending_enquiry_ts','nb_pending_deal_id','nb_pending_enquiry_token'].forEach(key=>sessionStorage.removeItem(key));}catch(err){}
    const btn=form.querySelector('button[type="submit"]');
    if(btn){btn.disabled=false;btn.removeAttribute('aria-disabled');if(btn.dataset.originalText)btn.textContent=btn.dataset.originalText;}
  }
  // Back navigation from the spam-check/provider page may restore a disabled
  // button from the browser's page cache. Restore the form for a genuine retry.
  window.addEventListener('pageshow',event=>{if(event.persisted){resetSubmission();form.querySelectorAll('.form-status').forEach(el=>el.remove());}});
});
