const content={scouting:{title:'Know what your scouts are doing.',description:'See monitoring status, capture cues, and recent audio and chat signals together. No guessing whether a scout is connected.',image:'scouting-demo.jpg',alt:'ClipBot scouts with fictional feeds and sample audio and chat signals'},dashboard:{title:'A clear view of your creative rhythm.',description:'See review decisions, candidates and example posting activity together. These sample numbers illustrate one creator’s workflow—not ClipBot’s customer usage.',image:'dashboard-demo.jpg',alt:'ClipBot dashboard populated with labeled sample review activity'}};

export function connectLandingControls(root=document){
 function activate(view){
  const c=content[view];if(!c)return;
  const landing=root.querySelector('.clipbot-landing');if(!landing)return;
  landing.querySelectorAll('[data-tour]').forEach(b=>{b.setAttribute('aria-selected',String(b.dataset.tour===view));b.tabIndex=b.dataset.tour===view?0:-1;});
  landing.querySelector('#tour-panel').setAttribute('aria-labelledby','tab-'+view);
  landing.querySelector('#tour-title').textContent=c.title;
  landing.querySelector('#tour-description').textContent=c.description;
  const img=landing.querySelector('#tour-image');img.src='/showcase/assets/'+c.image;img.alt=c.alt;
  landing.querySelector('#tour-link').href='/showcase/demo.html#'+view;
 }
 root.addEventListener('click',e=>{const tab=e.target.closest?.('[data-tour]');if(tab)activate(tab.dataset.tour);});
 root.addEventListener('keydown',e=>{
  const tab=e.target.closest?.('[data-tour]');if(!tab||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
  e.preventDefault();const buttons=[...root.querySelectorAll('.clipbot-landing [data-tour]')],i=buttons.indexOf(tab);
  const n=e.key==='Home'?0:e.key==='End'?buttons.length-1:(i+(e.key==='ArrowRight'?1:-1)+buttons.length)%buttons.length;
  activate(buttons[n].dataset.tour);buttons[n].focus();
 });
}
