/* Finance template: ordinary editable Builder fields plus an opt-in calculation mode. */
window.AlignFinance = {
  template(id) {
    const field=(id,label,type,required=true,extra={})=>({id,label,type,required,help:'',options:[],...extra});
    const recurring={category:['Monthly payment / bill','Repayment']}, repayment={category:['Repayment']};

const workflow={
  version:1,
  start_node:'finance_type',

  nodes:[
    {id:'finance_type',type:'choice',field_id:'category'},
    {id:'finance_name',type:'field',field_id:'name'},
    {id:'finance_label',type:'field',field_id:'label'},
    {id:'finance_amount',type:'field',field_id:'amount'},

    {id:'repayment_total_due',type:'field',field_id:'total_due'},
    {id:'repayment_no_due_date',type:'choice',field_id:'no_due_date'},
    {id:'repayment_due_date',type:'field',field_id:'due_date'},

    {id:'finance_next_payment',type:'field',field_id:'next_payment'},
    {id:'finance_frequency',type:'field',field_id:'frequency'},

    {id:'repayment_payment_mode',type:'choice',field_id:'payment_mode'},
    {id:'repayment_manual_payment',type:'field',field_id:'manual_payment'},

    {
      id:'finance_calculation',
      type:'calculation',
      operation:'finance_calculate',
      inputs:[
        'amount',
        'total_due',
        'no_due_date',
        'due_date',
        'next_payment',
        'frequency',
        'payment_mode',
        'manual_payment'
      ],
      outputs:[
        'payment_amount',
        'monthly_amount',
        'payment_count',
        'final_payment'
      ]
    },

    {
      id:'finance_summary',
      type:'summary',
      title:'Summary / Confirm',
      visible_fields:'current_branch'
    },

    {
      id:'finance_save',
      type:'save',
      record_type:'finance'
    },

    {
      id:'finance_home',
      type:'destination',
      screen:'finance_summary'
    }
  ],

  edges:[
    {from:'finance_type',to:'finance_name'},
    {from:'finance_name',to:'finance_label'},

    {
      from:'finance_label',
      to:'finance_amount',
      when:{field:'category',equals:'Monthly payment / bill'}
    },
    {
      from:'finance_amount',
      to:'finance_next_payment',
      when:{field:'category',equals:'Monthly payment / bill'}
    },

    {
      from:'finance_label',
      to:'repayment_total_due',
      when:{field:'category',equals:'Repayment'}
    },
    {
      from:'repayment_total_due',
      to:'repayment_no_due_date'
    },
    {
      from:'repayment_no_due_date',
      to:'repayment_due_date',
      when:{field:'no_due_date',equals:false}
    },
    {
      from:'repayment_no_due_date',
      to:'finance_next_payment',
      when:{field:'no_due_date',equals:true}
    },
    {
      from:'repayment_due_date',
      to:'finance_next_payment'
    },

    {
      from:'finance_next_payment',
      to:'finance_frequency'
    },
    {
      from:'finance_frequency',
      to:'finance_calculation',
      when:{field:'category',equals:'Monthly payment / bill'}
    },

    {
      from:'finance_frequency',
      to:'repayment_payment_mode',
      when:{field:'category',equals:'Repayment'}
    },
    {
      from:'repayment_payment_mode',
      to:'finance_calculation',
      when:{field:'payment_mode',equals:'Calculate from dates'}
    },
    {
      from:'repayment_payment_mode',
      to:'repayment_manual_payment',
      when:{field:'payment_mode',equals:'Enter payment amount'}
    },
    {
      from:'repayment_manual_payment',
      to:'finance_calculation'
    },

    {
      from:'finance_label',
      to:'finance_amount',
      when:{field:'category',equals:'One-off / wishlist'}
    },
    {
      from:'finance_amount',
      to:'finance_summary',
      when:{field:'category',equals:'One-off / wishlist'}
    },

    {
      from:'finance_calculation',
      to:'finance_summary'
    },

    {
      from:'finance_summary',
      to:'finance_save',
      action:'confirm'
    },
    {
      from:'finance_save',
      to:'finance_home',
      on:'success'
    }
  ]
};
	return {id,title:'Finance',workflow,description:'Bills, repayments and your wishlist in one place.',view:'table',finance:true,review_before_save:true,fields:[
  field('category','What would you like to add?','select',true,{options:['Monthly payment / bill','Repayment','One-off / wishlist']}),
  field('name','Name','text'),
      field('label','Label','select',true,{options:['Home','Utilities','Transport','Personal','Other'],allow_custom:true,help:'Choose a label or type a new one.'}),
      field('amount','Amount (£)','number',true,{show_when:{category:['Monthly payment / bill','One-off / wishlist']}}),
      field('total_due','Total amount due (£)','number',true,{show_when:repayment}),
      field('no_due_date','No final due date (N/A)','checkbox',false,{show_when:repayment}),
      field('due_date','Final due date','date',true,{show_when:{...repayment,no_due_date:[false]}}),
      field('next_payment','Next payment date','date',true,{show_when:recurring}),
      field('frequency','Payment frequency','select',true,{options:['Weekly','Fortnightly','Monthly','Quarterly','Yearly'],show_when:recurring}),
      field('payment_mode','How would you like to set this repayment?','select',true,{options:['Calculate from dates','Enter payment amount'],show_when:repayment,help:'Choose separately for each repayment. With no final due date, enter the amount yourself.'}),
      field('manual_payment','Payment amount (£)','number',true,{show_when:{...repayment,payment_mode:['Enter payment amount']}})
    ]};
  },
  money(value) {return new Intl.NumberFormat('en-GB',{style:'currency',currency:'GBP'}).format(Number(value)||0);},
  date(value) {if(!value)return '—';return formatDisplayDate(value)||'—';},
  review(values) {
    const e=AlignFields.escape;
    return `<p><strong>Payment amount: ${e(this.money(values.payment_amount))}</strong></p>${values.category==='One-off / wishlist'?'<p>Not included in monthly outgoings.</p>':`<p>Monthly equivalent: ${e(this.money(values.monthly_amount))}</p>`}${values.payment_count?`<p>${e(values.payment_count)} payments; final payment ${e(this.money(values.final_payment))}.</p><p class="helper">Calculation excludes interest and fees. Monthly payments keep the original day, or the last day of shorter months.</p>`:''}`;
  },
  summary(records,actions) {
    const e=AlignFields.escape, sum=rows=>rows.reduce((n,r)=>n+Math.round(Number(r.values.monthly_amount||0)*100),0)/100;
    const valid=records.filter(r=>!r.calculation_error);
    return `<article class="card"><h2>Total monthly outgoings</h2><p style="font-size:1.6rem;font-weight:700">${e(this.money(sum(valid)))}</p><p class="helper">Monthly equivalents for the records shown. Weekly × 52 ÷ 12; fortnightly × 26 ÷ 12. Wishlist excluded. This is a budget estimate, not a payment forecast.</p></article>`+
      ['Monthly payment / bill','Repayment','One-off / wishlist'].map(category=>{
        const rows=records.filter(r=>r.values.category===category);
        if(!rows.length)return '';
        const subtotal=this.money(sum(rows.filter(r=>!r.calculation_error)));
        return `<section class="card"><h2>${e(category)}</h2>${rows.map(r=>`<article style="display:flex;flex-wrap:wrap;align-items:center;gap:12px;padding:14px 0;border-bottom:1px solid #ddd"><div style="flex:1;min-width:150px"><strong>${e(r.values.name||r.values.label)}</strong><div>${e(r.values.label)}</div>${category!=='One-off / wishlist'?`<small>Next payment: ${e(this.date(r.values.next_payment))} · ${e(r.values.frequency)}</small>`:''}</div><div><strong>${r.calculation_error?'Needs attention':e(this.money(r.values.payment_amount))}</strong>${category!=='One-off / wishlist'?`<small style="display:block">${e(this.money(r.values.monthly_amount))}/month</small>`:''}</div>${actions(r)}${r.calculation_error?`<p role="alert">${e(r.calculation_error)} — excluded from totals.</p>`:''}</article>`).join('')}${category!=='One-off / wishlist'?`<p><strong>Monthly subtotal: ${e(subtotal)}</strong></p>`:''}</section>`;
      }).join('');
  }
};
