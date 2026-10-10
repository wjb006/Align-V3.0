from pathlib import Path
r=Path(__file__).resolve().parents[1]; p=r/'static'
path=r/'owner_builder.py'; s=path.read_text(encoding='utf-8')
s=s.replace('def validate(doc, previous=None):', '''def formatting_validate(value):
    if not isinstance(value, dict): raise BuilderError('Invalid formatting settings.')
    result = {}
    for key, default in [('accent','#365ce6'),('background','#f5f7fb'),('surface','#ffffff'),('text','#1c2940')]:
        colour=value.get(key,default)
        if not isinstance(colour,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',colour): raise BuilderError('Choose a valid formatting colour.')
        result[key]=colour
    for key, choices, default in [('font',('system','serif','mono'),'system'),('size',('14','16','18','20'),'16'),('spacing',('compact','comfortable','roomy'),'comfortable'),('radius',('0','8','16','24'),'16'),('columns',('1','2'),'1'),('heading',('normal','bold'),'bold'),('align',('left','center'),'left')]:
        selected=value.get(key,default)
        if selected not in choices: raise BuilderError('Choose a valid formatting '+key+'.')
        result[key]=selected
    return result


def validate(doc, previous=None):''')
s=s.replace('clean = dict(startup=startup,', "clean = dict(formatting=formatting_validate(doc.get('formatting', {})), startup=startup,")
path.write_text(s,encoding='utf-8')
path=p/'builder-fields.js'; s=path.read_text(encoding='utf-8')
s+='''
window.AlignFormatting = {
  defaults: {accent:'#365ce6',background:'#f5f7fb',surface:'#ffffff',text:'#1c2940',font:'system',size:'16',spacing:'comfortable',radius:'16',columns:'1',heading:'bold',align:'left'},
  apply(root, config) {
    if(!root)return;
    const f={...this.defaults,...config};
    root.classList.add('align-formatted');
    for(const key of ['accent','background','surface','text'])root.style.setProperty('--edit-'+key,/^#[0-9a-f]{6}$/i.test(f[key])?f[key]:this.defaults[key]);
    const values={font:{system:'system-ui, sans-serif',serif:'Georgia, serif',mono:'Consolas, monospace'},size:{14:'14px',16:'16px',18:'18px',20:'20px'},spacing:{compact:'10px',comfortable:'18px',roomy:'26px'},radius:{0:'0px',8:'8px',16:'16px',24:'24px'},columns:{1:'1',2:'2'},heading:{normal:'400',bold:'700'},align:{left:'left',center:'center'}};
    for(const [key,map] of Object.entries(values))root.style.setProperty('--edit-'+key,map[f[key]]||map[this.defaults[key]]);
  }
};
'''; path.write_text(s,encoding='utf-8')
path=p/'owner-builder.js';s=path.read_text(encoding='utf-8')
s=s.replace('  function editIndex() {', '''  function formattingEditor() {
    const f={...AlignFormatting.defaults,...doc.formatting};
    const select=(label,key,items)=>`<label class="field">${e(label)}<select data-format="${key}">${options(items,f[key])}</select></label>`;
    return `<h2>Formatting</h2><p class="helper">Style published app pages and forms. The editor controls keep their own appearance. Two-column forms stack on small screens.</p><div class="builder-two">${[['accent','Button colour'],['background','Page background'],['surface','Card background'],['text','Text colour']].map(([key,label])=>`<label class="field">${label}<input type="color" data-format="${key}" value="${e(f[key])}"></label>`).join('')}${select('Font','font',{system:'System sans serif',serif:'Serif',mono:'Monospace'})}${select('Text size','size',{14:'Small · 14 px',16:'Standard · 16 px',18:'Large · 18 px',20:'Extra large · 20 px'})}${select('Spacing','spacing',{compact:'Compact',comfortable:'Comfortable',roomy:'Roomy'})}${select('Corners','radius',{0:'Square',8:'Slightly rounded',16:'Rounded',24:'Very rounded'})}${select('Form columns','columns',{1:'One',2:'Two'})}${select('Heading weight','heading',{normal:'Regular',bold:'Bold'})}${select('Heading alignment','align',{left:'Left',center:'Centre'})}</div><button class="secondary-button" data-format-reset>Reset formatting</button>`;
  }
  function editIndex() {''')
s=s.replace("{title:doc.startup.title", "{title:'Formatting',detail:'Colours, fonts, spacing, corners and form columns',tab:'formatting'},\n      {title:doc.startup.title")
s=s.replace("if(tab==='overview') {", "if(tab==='formatting') { editor=formattingEditor();preview=`<div class=\"builder-preview\"><h2>${e(doc.startup.title)}</h2><p>${e(doc.startup.description)}</p>${previewFields(doc.startup.fields)}<button class=\"primary-button\">${e(doc.startup.button)}</button><article class=\"card\"><h3>Example card</h3><p>Preview your colours, type and spacing here.</p></article></div>`; } else if(tab==='overview') {")
s=s.replace('    controls();\n  }', "    AlignFormatting.apply($('#builder-content aside'),doc.formatting);\n    controls();\n  }")
s=s.replace("const el=ev.target,key=el.dataset.prop||'';", "const el=ev.target,key=el.dataset.prop||'';\n    if(el.dataset.format){if(busy||!doc)return;changed();doc.formatting={...AlignFormatting.defaults,...doc.formatting,[el.dataset.format]:el.value};render(true);status('Formatting updated. Save draft or review before publishing.');return;}")
s=s.replace("if(b.dataset.jump){", "if(b.hasAttribute('data-format-reset')){changed();doc.formatting={...AlignFormatting.defaults};render();return;}\n    if(b.dataset.jump){")
path.write_text(s,encoding='utf-8')
path=p/'owner-builder.html';s=path.read_text(encoding='utf-8').replace('<button data-tab="review"','<button data-tab="formatting" aria-pressed="false">Formatting</button><button data-tab="review"').replace('150-edit1','150-format1');path.write_text(s,encoding='utf-8')
path=p/'app.js';s=path.read_text(encoding='utf-8').replace('function render() {','function render() {\n  AlignFormatting.apply(document.body,state.boot?.builder?.document?.formatting);').replace('150-otp1','150-format1');path.write_text(s,encoding='utf-8')
for name in ['index.html','service-worker.js']:
    path=p/name;s=path.read_text(encoding='utf-8').replace('150-otp1','150-format1').replace('${BUILD}-otp1','${BUILD}-format1');path.write_text(s,encoding='utf-8')
with (p/'owner-builder.css').open('a',encoding='utf-8') as f:f.write('''
.align-formatted{background:var(--edit-background);color:var(--edit-text);font-family:var(--edit-font);font-size:var(--edit-size)}
.align-formatted :is(.card,.builder-preview,.quick-action){background:var(--edit-surface);color:var(--edit-text);border-radius:var(--edit-radius);padding:var(--edit-spacing)}
.align-formatted :is(h1,h2,h3){font-family:var(--edit-font);font-weight:var(--edit-heading);text-align:var(--edit-align);color:var(--edit-text)}
.align-formatted :is(p,label,input,textarea,select,.quick-action){font-family:var(--edit-font);font-size:var(--edit-size)}
.align-formatted .primary-button{background:var(--edit-accent);border-radius:var(--edit-radius)}
.align-formatted .settings-form{display:grid;grid-template-columns:repeat(var(--edit-columns),minmax(0,1fr));gap:var(--edit-spacing)}
.align-formatted .settings-form>.field{margin:0;min-width:0}
.align-formatted .settings-form>:not(.field){grid-column:1/-1}
.align-formatted .field :is(input,textarea,select){border-radius:var(--edit-radius);padding:10px;box-sizing:border-box;max-width:100%}
.align-formatted .settings-form>.field label{display:block;margin-bottom:6px}
.phone-preview .align-formatted .settings-form{grid-template-columns:1fr}
@media(max-width:600px){.align-formatted .settings-form{grid-template-columns:1fr}}
''')
