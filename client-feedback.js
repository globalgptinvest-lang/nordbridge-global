(function(){
  'use strict';
  const copy={
    en:{
      kicker:'CLIENT FEEDBACK',
      title:'Honest feedback from real client work.',
      body:'Have you worked with NordBridge? Share your honest experience. We publish comments only with your permission; positive and critical feedback are both welcome.',
      cta:'Share your experience',
      subject:'NordBridge client feedback',
      mailBody:'Please share your honest feedback about working with NordBridge. If you agree to publication, tell us the exact name or company you permit us to display. Sharing feedback is optional and does not affect any service.'
    },
    uk:{
      kicker:'ВІДГУКИ КЛІЄНТІВ',
      title:'Чесні відгуки про реальну співпрацю.',
      body:'Працювали з NordBridge? Поділіться чесним враженням. Публікуємо відгук лише за вашою згодою; позитивні й критичні відгуки однаково вітаються.',
      cta:'Поділитися відгуком',
      subject:'Відгук клієнта NordBridge',
      mailBody:'Будь ласка, поділіться чесним враженням про співпрацю з NordBridge. Якщо ви дозволяєте опублікувати відгук, вкажіть точне ім’я або назву компанії, яку можна показати. Відгук необов’язковий і не впливає на отримання послуг.'
    },
    da:{
      kicker:'KUNDEFEEDBACK',
      title:'Ærlig feedback fra reelle samarbejder.',
      body:'Har du arbejdet med NordBridge? Del din ærlige oplevelse. Vi offentliggør kun kommentarer med din tilladelse; både positive og kritiske tilbagemeldinger er velkomne.',
      cta:'Del din oplevelse',
      subject:'Kundefedback til NordBridge',
      mailBody:'Del venligst din ærlige oplevelse med NordBridge. Hvis du giver tilladelse til offentliggørelse, bedes du skrive det præcise navn eller firmanavn, som må vises. Feedback er frivillig og påvirker ikke nogen ydelse.'
    },
    ar:{
      kicker:'آراء العملاء',
      title:'تجارب حقيقية من تعاون فعلي.',
      body:'هل سبق لك العمل مع NordBridge؟ شاركنا رأيك بصراحة. لا ننشر أي تعليق إلا بموافقتك؛ ونرحب بالملاحظات الإيجابية والنقدية.',
      cta:'شارك تجربتك',
      subject:'ملاحظات عميل NordBridge',
      mailBody:'يرجى مشاركة رأيك الصادق حول العمل مع NordBridge. إذا وافقت على نشر تعليقك، اذكر الاسم أو اسم الشركة بدقة كما تسمح بعرضه. المشاركة اختيارية ولا تؤثر في أي خدمة.'
    }
  };
  function update(lang){
    const selected=copy[lang]||copy.en;
    document.querySelectorAll('[data-nb-feedback]').forEach(element=>{
      const key=element.getAttribute('data-nb-feedback');
      if(selected[key]) element.textContent=selected[key];
    });
    const link=document.querySelector('[data-nb-feedback-link]');
    if(link){
      link.textContent=selected.cta;
      link.href='mailto:info@nordbridge-global.com?subject='+encodeURIComponent(selected.subject)+'&body='+encodeURIComponent(selected.mailBody);
    }
  }
  window.addEventListener('nordbridge:languagechange',event=>update(event.detail&&event.detail.lang));
  update(document.documentElement.lang||'en');
})();