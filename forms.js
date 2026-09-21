document.querySelectorAll('.lead-form').forEach(form=>{
  if(!form.querySelector('input[name="_honey"]')){
    const honey=document.createElement('input');
    honey.type='text';honey.name='_honey';honey.autocomplete='off';honey.tabIndex=-1;honey.className='form-honey';
    honey.setAttribute('aria-hidden','true');form.appendChild(honey);
  }
  if(!form.querySelector('.privacy-consent')){
    const consent=document.createElement('label');
    consent.className='privacy-consent';
    consent.innerHTML='<span><input type="checkbox" name="privacy_consent" value="accepted" required> I agree that NordBridge may use the information submitted here to review and respond to this business enquiry. <a href="privacy.html" target="_blank" rel="noopener">Privacy Notice</a>.</span>';
    const btn=form.querySelector('button[type="submit"]');
    form.insertBefore(consent,btn);
  }
  form.addEventListener('submit',async e=>{
    e.preventDefault();
    if(!form.reportValidity()) return;
    const btn=form.querySelector('button[type="submit"]');
    const original=btn.textContent;
    const lang=document.documentElement.lang||'en';
    const msg={
      en:{sending:'Sending…',sent:'Sent ✓',ok:'Thank you. Your enquiry has been sent to NordBridge.',fail:'Could not send automatically. Please use WhatsApp or email info@nordbridge-global.com.'},
      uk:{sending:'Надсилання…',sent:'Надіслано ✓',ok:'Дякуємо. Ваш запит надіслано до NordBridge.',fail:'Не вдалося надіслати автоматично. Скористайтеся WhatsApp або email info@nordbridge-global.com.'},
      da:{sending:'Sender…',sent:'Sendt ✓',ok:'Tak. Din henvendelse er sendt til NordBridge.',fail:'Kunne ikke sende automatisk. Brug WhatsApp eller email info@nordbridge-global.com.'},
      ar:{sending:'جارٍ الإرسال…',sent:'تم الإرسال ✓',ok:'شكرًا لك. تم إرسال استفسارك إلى NordBridge.',fail:'تعذر الإرسال تلقائيًا. يرجى استخدام WhatsApp أو البريد info@nordbridge-global.com.'}
    }[lang]||null;
    const t=msg||{sending:'Sending…',sent:'Sent ✓',ok:'Thank you. Your enquiry has been sent to NordBridge.',fail:'Could not send automatically. Please use WhatsApp or email info@nordbridge-global.com.'};
    btn.disabled=true;btn.textContent=t.sending;
    const fd=new FormData(form);
    fd.set('_subject',form.dataset.mailSubject||'NordBridge website enquiry');
    fd.set('_template','table');
    fd.set('_captcha','false');
    fd.set('_url',location.href);
    const email=form.querySelector('input[type="email"]');
    if(email&&email.value) fd.set('_replyto',email.value);
    let note=form.querySelector('.form-status');
    if(!note){note=document.createElement('p');note.className='form-status';note.setAttribute('role','status');note.setAttribute('aria-live','polite');form.appendChild(note);}
    try{
      const r=await fetch('https://formsubmit.co/ajax/b725f79abde568a9761c73d482dca435',{method:'POST',headers:{'Accept':'application/json'},body:fd});
      const data=await r.json().catch(()=>({}));
      if(!r.ok||data.success===false) throw new Error('send failed');
      form.reset();btn.textContent=t.sent;note.textContent=t.ok;note.classList.remove('error');note.classList.add('success');
    }catch(err){
      btn.textContent=original;note.textContent=t.fail;note.classList.remove('success');note.classList.add('error');
    }finally{
      setTimeout(()=>{btn.disabled=false;if(btn.textContent===t.sent)btn.textContent=original;},5000);
    }
  });
});