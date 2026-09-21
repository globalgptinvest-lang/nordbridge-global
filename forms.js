document.querySelectorAll('.lead-form').forEach(form=>{
  form.action='https://formsubmit.co/b725f79abde568a9761c73d482dca435';
  form.method='POST';

  const addHidden=(name,value)=>{
    let input=form.querySelector('input[name="'+name+'"]');
    if(!input){input=document.createElement('input');input.type='hidden';input.name=name;form.appendChild(input);}
    input.value=value;
    return input;
  };

  addHidden('_subject',form.dataset.mailSubject||'NordBridge website enquiry');
  addHidden('_template','table');
  addHidden('_captcha','false');
  addHidden('_next','https://nordbridge-global.com/thanks.html');
  addHidden('_url',location.href);

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

  form.addEventListener('submit',()=>{
    if(!form.reportValidity()) return;
    const email=form.querySelector('input[type="email"]');
    if(email&&email.value) addHidden('_replyto',email.value);
    addHidden('_url',location.href);
    const btn=form.querySelector('button[type="submit"]');
    if(btn){
      const lang=document.documentElement.lang||'en';
      const sending={en:'Sending…',uk:'Надсилання…',da:'Sender…',ar:'جارٍ الإرسال…'}[lang]||'Sending…';
      btn.disabled=true;btn.textContent=sending;
    }
  });
});