/* Align Build 153 — live event entry and saved-contact management. */
(() => {
  const A = window.ALIGN152 = { favourites: [], loaded: false, renderCalendarOriginal: null };
  let contactManagerOverlay = null;
  let contactManagerReturnFocus = null;

  async function loadFavourites() {
    try {
      const data = await api('/api/favourites');
      A.favourites = data.favourites || [];
      A.loaded = true;
      enhanceVisibleUI();
    } catch (_) {
      A.favourites = [];
      A.loaded = true;
    }
  }

  function fav(type, key) {
    return A.favourites.find(x => x.entity_type === type && x.entity_key === String(key));
  }

  async function toggleFavourite(type, key, label, value = '', metadata = {}) {
    const existing = fav(type, key);
    try {
      const data = await api('/api/favourites', {
        method: 'POST',
        body: { entity_type:type, entity_key:String(key), label, value, metadata, active:!existing }
      });
      A.favourites = A.favourites.filter(x => !(x.entity_type === type && x.entity_key === String(key)));
      if (data.favourite) A.favourites.push(data.favourite);
      enhanceVisibleUI();
      toast(existing ? 'Removed from favourites.' : 'Saved to favourites.');
    } catch (error) { toast(error.message); }
  }

  function titleSuggestions() {
    const fromEvents = (state.sectionData?.events || [])
      .filter(e => e.source_kind === 'align' && e.title)
      .map(e => e.title);
    const fromFavs = A.favourites
      .filter(x => x.entity_type === 'event_title' && x.label)
      .map(x => x.label);
    return [...new Set([...fromFavs, ...fromEvents])].slice(0, 40);
  }

  function locationSuggestions() {
    return A.favourites
      .filter(x => x.entity_type === 'location' || x.entity_type === 'event_location')
      .map(x => ({label:x.label, value:x.value || x.label}))
      .filter(x => x.value);
  }
  let contacts = [];
  A.contacts = contacts;
  function refreshContactSelects() {
    document.querySelectorAll('form[data-form="organiser-event"] [data-build152-contact]').forEach(select => {
      const form = select.closest('form');
      const saved = contactFromNote(form?.elements.notes?.value || '');
      const selected = select.value || saved?.id || '';
      select.innerHTML = '<option value="">None / enter manually</option>' + contacts.map(c =>
        '<option value="' + escapeHtml(c.id) + '">' +
        escapeHtml(c.name + (c.address ? ' · ' + c.address : '')) +
        '</option>'
      ).join('');
      if (contacts.some(c => String(c.id) === String(selected))) select.value = String(selected);
      renderContactPreview(form);
      const selectedContact = contacts.find(item => String(item.id) === String(select.value));
      const location = form?.elements.location;
      const previousAddress = form?.dataset.build153AutoContactAddress || '';
      if (selectedContact?.address && location && location.value.trim() === previousAddress) {
        location.value = selectedContact.address;
        form.dataset.build153AutoContactAddress = selectedContact.address;
      }
    });
  }
  async function loadContacts() {
    let data;
    try {
      data = await api('/api/contacts');
    } catch (_) {
      contacts = [];
      A.contacts = contacts;
      refreshContactSelects();
      return;
    }
    contacts = data.contacts || [];
    A.contacts = contacts;
    refreshContactSelects();
    refreshContactAwarePage();
  }
  function contactFromNote(notes) {
    const match = String(notes || '').match(/\[Align contact\]\s*(\{.*?\})(?:\n|$)/);
    if (!match) return null;
    try { return JSON.parse(match[1]); } catch (_) { return null; }
  }
  function currentContact(contact) {
    if (!contact?.id) return contact;
    return contacts.find(item => String(item.id) === String(contact.id)) || contact;
  }
  function contactDetailsMarkup(contact, className = 'build153-contact-details') {
    if (!contact) return '';
    const phone = String(contact.phone || '').trim();
    return `<div class="${className}"><strong>Contact · ${escapeHtml(contact.name || '')}</strong>` +
      `${contact.address ? `<span>${escapeHtml(contact.address)}</span>` : ''}` +
      `${phone ? `<a href="tel:${encodeURIComponent(phone)}">☎ ${escapeHtml(phone)}</a>` : ''}</div>`;
  }
  function eventContactMarkup(notes) {
    return contactDetailsMarkup(currentContact(contactFromNote(notes)));
  }
  A.eventContactMarkup = eventContactMarkup;
  function refreshContactAwarePage() {
    enhanceVisibleUI();
    if (state?.boot && typeof window.render === 'function') window.render();
  }
  function renderContactPreview(form) {
    const preview = form?.querySelector('[data-build153-contact-preview]');
    if (!preview) return;
    const selected = contacts.find(item => String(item.id) === String(form.elements.align_contact_id?.value));
    preview.innerHTML = contactDetailsMarkup(selected) || '<p class="helper">No saved contact selected.</p>';
  }
  function contactMatchesQuery(query) {
    const q = String(query || '').trim().toLowerCase();
    if (!q) return contacts;
    return contacts.filter(c => [c.name,c.address,c.phone].some(v => String(v || '').toLowerCase().includes(q)));
  }

  function smartDateTime(phrase, now = new Date()) {
    const source = String(phrase || '');
    let text = source;
    const base = new Date(now);
    base.setHours(12, 0, 0, 0);
    let date = null;
    let match = text.match(/\b(today|tomorrow)\b/i);
    if (match) {
      date = new Date(base);
      if (match[1].toLowerCase() === 'tomorrow') date.setDate(date.getDate() + 1);
      text = text.replace(match[0], ' ');
    } else if ((match = text.match(/\b(next\s+)?(sun(?:day)?|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?)\b/i))) {
      const weekdays = ['sun','mon','tue','wed','thu','fri','sat'];
      const target = weekdays.findIndex(day => match[2].toLowerCase().startsWith(day));
      date = new Date(base);
      let offset = (target - date.getDay() + 7) % 7;
      if (offset === 0 || match[1]) offset += 7;
      date.setDate(date.getDate() + offset);
      text = text.replace(match[0], ' ');
    } else if ((match = text.match(/\b(\d{1,2})\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:\s+(\d{4}))?\b/i))) {
      const months = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'];
      const month = months.findIndex(name => match[2].toLowerCase().startsWith(name));
      const year = Number(match[3] || base.getFullYear());
      date = new Date(year, month, Number(match[1]), 12);
      if (!match[3] && date < base) date.setFullYear(date.getFullYear() + 1);
      if (date.getDate() !== Number(match[1])) date = null;
      text = text.replace(match[0], ' ');
    } else if ((match = text.match(/\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b/))) {
      const day = Number(match[1]), month = Number(match[2]) - 1;
      let year = Number(match[3] || base.getFullYear());
      if (year < 100) year += 2000;
      date = new Date(year, month, day, 12);
      if (!match[3] && date < base) date.setFullYear(date.getFullYear() + 1);
      if (date.getDate() !== day || date.getMonth() !== month) date = null;
      text = text.replace(match[0], ' ');
    }
    const time = text.match(/\b(?:at\s*)?(\d{1,2})(?::([0-5]\d))?\s*(am|pm)\b/i) ||
      text.match(/\b(?:at\s*)?([01]?\d|2[0-3]):([0-5]\d)\b/i) ||
      text.match(/\bat\s*([01]?\d|2[0-3])\b/i);
    if (!date || !time) return null;
    let hour = Number(time[1]), minute = Number(time[2] || 0);
    if (time[3]) { const meridiem = time[3].toLowerCase(); hour = hour % 12 + (meridiem === 'pm' ? 12 : 0); }
    if (hour > 23) return null;
    text = text.replace(time[0], ' ').replace(/\b(?:on)\b/gi, ' ').replace(/[\s,·-]+$/g, '').trim();
    let location = '';
    const at = text.match(/^(.+?)\s+at\s+(.+)$/i);
    if (at) {
      text = at[1];
      location = at[2];
    }
    const clean = value => value.replace(/^[\s,·-]+|[\s,·-]+$/g, '').trim();
    text = clean(text.replace(/\bat$/i, ''));
    location = clean(location);
    const start = new Date(date);
    start.setHours(hour, minute, 0, 0);
    const end = new Date(start.getTime() + 60 * 60000);
    const isoDate = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    const clock = d => `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
    return {date:isoDate(start), start:clock(start), end:clock(end), title:text || source, location};
  }
  A.smartDateTime = smartDateTime;
  function contactMarkup(selectedId='') {
    const options = contacts.map(c =>
      '<option value="' + escapeHtml(c.id) + '" ' + (String(c.id)===String(selectedId)?'selected':'') + '>' +
      escapeHtml(c.name + (c.address ? ' · ' + c.address : '')) + '</option>'
    ).join('');
    return '<div class="field build152-contact-field"><label>Contact</label><select name="align_contact_id" data-build152-contact><option value="">None / enter manually</option>' + options + '</select><small class="helper">Linked contact details are read-only here. Edit them separately in Saved contacts.</small><div data-build153-contact-preview></div><button type="button" class="small-button" data-build153-manage-contacts>Manage saved contacts</button></div>';
  }
  async function saveContact(contact) {
    const data = await api('/api/contacts', {method:'POST', body:contact});
    const saved = data.contact;
    if (saved) {
      contacts = [...contacts.filter(c => c.id !== saved.id), saved].sort((a,b) => a.name.localeCompare(b.name));
      A.contacts = contacts;
      refreshContactSelects();
      refreshContactAwarePage();
    }
    return saved;
  }
  function openContactManager(initial = null) {
    const root = document.querySelector('#modal-root');
    if (!root) return;
    if (contactManagerOverlay) contactManagerOverlay.remove();
    contactManagerReturnFocus = document.activeElement;
    contactManagerOverlay = document.createElement('div');
    contactManagerOverlay.className = 'modal-backdrop build153-contact-manager-backdrop';
    contactManagerOverlay.innerHTML = '<section class="modal" role="dialog" aria-modal="true" tabindex="-1" aria-label="Saved contacts"><div class="modal-head"><h2>Saved contacts</h2><button type="button" class="close" data-build153-contact-action="close" aria-label="Close">×</button></div><div class="build153-contact-body"></div></section>';
    root.appendChild(contactManagerOverlay);
    document.querySelector('.app-shell')?.setAttribute('inert', '');

    const body = contactManagerOverlay.querySelector('.build153-contact-body');
    const showList = () => {
      body.innerHTML = `<p class="helper">Contact details stay read-only on events. Edit a saved contact here to update its linked event details.</p><div class="master-list">${contacts.map(contact => `<article class="card master-item"><div class="item-content"><strong>${escapeHtml(contact.name)}</strong>${contact.address ? `<small>${escapeHtml(contact.address)}</small>` : ''}${contact.phone ? `<a href="tel:${encodeURIComponent(contact.phone)}">${escapeHtml(contact.phone)}</a>` : ''}</div><button type="button" class="small-button" data-build153-contact-action="edit" data-id="${contact.id}">Edit</button></article>`).join('') || '<p>No saved contacts yet.</p>'}</div><div class="modal-actions"><button type="button" class="secondary-button" data-build153-contact-action="close">Done</button><button type="button" class="primary-button" data-build153-contact-action="new">＋ Add contact</button></div>`;
      body.querySelector('[data-build153-contact-action="new"]')?.focus();
    };
    const showForm = contact => {
      const item = contact || initial || {name:'',address:'',phone:'',notes:''};
      initial = null;
      body.innerHTML = `<form class="form-grid" data-build153-contact-form data-id="${item.id || ''}"><p class="helper">Events show these details read-only. Change them here to update linked event details.</p><div class="field"><label>Name</label><input name="name" required maxlength="160" value="${escapeHtml(item.name || '')}"></div><div class="field"><label>Address or location</label><input name="address" maxlength="500" value="${escapeHtml(item.address || '')}"></div><div class="field"><label>Phone number</label><input name="phone" type="tel" maxlength="80" autocomplete="tel" value="${escapeHtml(item.phone || '')}"></div><div class="field"><label>Notes</label><textarea name="notes" maxlength="1000">${escapeHtml(item.notes || '')}</textarea></div><p class="helper" role="alert" data-build153-contact-error></p><div class="modal-actions"><button type="button" class="secondary-button" data-build153-contact-action="back">Back</button><button class="primary-button">Save contact</button></div></form>`;
      body.querySelector('input[name="name"]')?.focus();
    };
    contactManagerOverlay.addEventListener('click', event => {
      const button = event.target.closest('[data-build153-contact-action]');
      if (!button) return;
      const action = button.dataset.build153ContactAction;
      if (action === 'close') {
        contactManagerOverlay.remove();
        contactManagerOverlay = null;
        document.querySelector('.app-shell')?.toggleAttribute('inert', !!root.querySelector('.modal-backdrop'));
        if (contactManagerReturnFocus?.isConnected) contactManagerReturnFocus.focus();
        contactManagerReturnFocus = null;
      } else if (action === 'new') showForm(null);
      else if (action === 'back') showList();
      else if (action === 'edit') showForm(contacts.find(item => String(item.id) === button.dataset.id));
    });
    contactManagerOverlay.addEventListener('submit', async event => {
      const form = event.target.closest('[data-build153-contact-form]');
      if (!form) return;
      event.preventDefault();
      const submit = form.querySelector('.primary-button');
      submit.disabled = true;
      try {
        const values = Object.fromEntries(new FormData(form));
        const id = form.dataset.id;
        const data = await api(id ? `/api/contacts/${id}` : '/api/contacts', {method:id ? 'PUT' : 'POST', body:values});
        const saved = data.contact;
        if (!saved) throw new Error('The contact could not be saved.');
        contacts = [...contacts.filter(item => String(item.id) !== String(saved.id)), saved].sort((a,b) => a.name.localeCompare(b.name));
        A.contacts = contacts;
        refreshContactSelects();
        refreshContactAwarePage();
        showList();
        toast('Saved contact updated.');
      } catch (error) {
        form.querySelector('[data-build153-contact-error]').textContent = error.message;
      } finally {
        if (submit.isConnected) submit.disabled = false;
      }
    });
    if (initial) showForm(initial);
    else showList();
  }
  async function importPhoneContact(form) {
    if (!navigator.contacts?.select) {
      toast('Phone contact import is not available in this browser. Save the contact in Align instead.');
      return;
    }
    try {
      const picked = await navigator.contacts.select(['name','tel','address'], {multiple:false});
      const item = picked?.[0];
      if (!item) return;
      const name = Array.isArray(item.name) ? item.name.join(' ').trim() : String(item.name || '').trim();
      const phone = Array.isArray(item.tel) ? String(item.tel[0] || '') : String(item.tel || '');
      const rawAddress = Array.isArray(item.address) ? item.address[0] : item.address;
      const address = rawAddress && typeof rawAddress === 'object'
        ? [rawAddress.addressLine, rawAddress.city, rawAddress.region, rawAddress.postalCode, rawAddress.country].filter(Boolean).join(', ')
        : String(rawAddress || '');
      if (!name) { toast('That contact has no name.'); return; }
      const saved = await saveContact({name,address,phone});
      const select = form.querySelector('[data-build152-contact]');
      if (select) {
        select.innerHTML = '<option value="">None / enter manually</option>' + contacts.map(c => '<option value="' + escapeHtml(c.id) + '">' + escapeHtml(c.name + (c.address ? ' · ' + c.address : '')) + '</option>').join('');
        select.value = String(saved.id);
        select.dispatchEvent(new Event('change', {bubbles:true}));
      }
      toast('Contact imported and saved to Align.');
    } catch (error) {
      if (error?.name !== 'AbortError') toast(error.message || 'Could not import that contact.');
    }
  }

  function decorateEventContacts() {
    const events = state.sectionData?.events || [];
    document.querySelectorAll('.organiser-event').forEach(card => {
      const button = card.querySelector('[data-action="edit-section-event"]');
      const event = button ? events.find(item => String(item.id) === String(button.dataset.id)) : null;
      const details = event && eventContactMarkup(event.notes);
      const existing = card.querySelector('[data-build153-event-contact]');
      if (!details) { existing?.remove(); return; }
      const wrapper = document.createElement('div');
      wrapper.dataset.build153EventContact = '1';
      wrapper.innerHTML = details;
      if (existing) existing.replaceWith(wrapper);
      else card.querySelector('.item-content')?.appendChild(wrapper);
    });
  }

  function enhanceEventForm(form) {
    if (!form || form.dataset.build152Enhanced === '1') return;
    form.dataset.build152Enhanced = '1';

    const title = form.elements.title;
    if (title) {
      const id = 'align152-title-suggestions';
      title.setAttribute('list', id);
      const dl = document.createElement('datalist');
      dl.id = id;
      titleSuggestions().forEach(value => {
        const option = document.createElement('option');
        option.value = value;
        dl.appendChild(option);
      });
      form.appendChild(dl);

      const hint = document.createElement('small');
      hint.className = 'build152-smart-hint';
      hint.setAttribute('role', 'status');
      hint.setAttribute('aria-live', 'polite');
      hint.textContent = 'Type an event, place, date and time, such as “Doctors at St Catherines 09/10/26 at 11”.';
      title.insertAdjacentElement('afterend', hint);

      title.addEventListener('input', () => {
        const parsed = smartDateTime(title.value);
        const location = form.elements.location;
        if (parsed && form.elements.date && form.elements.start_time && form.elements.end_time) {
          form.elements.date.value = parsed.date;
          form.elements.start_time.value = parsed.start;
          form.elements.end_time.value = parsed.end;
          if (form.elements.all_day) form.elements.all_day.checked = false;
          hint.textContent = `Suggestion: ${parsed.title || 'event'} on ${parsed.date} at ${parsed.start}. Review the date, time and location below before saving.`;
          const currentLocation = location?.value.trim() || '';
          const previousAutoLocation = form.dataset.build153AutoLocation || '';
          const previousContactAddress = form.dataset.build153AutoContactAddress || '';
          if (parsed.location && location && (!currentLocation || currentLocation === previousAutoLocation || currentLocation === previousContactAddress)) {
            location.value = parsed.location;
            form.dataset.build153AutoLocation = parsed.location;
            form.dataset.build153AutoContactAddress = '';
          }
        }
        const query = parsed
          ? `${parsed.title} ${parsed.location}`.trim()
          : title.value.trim().replace(/^appointment\s+at\s+/i, '');
        const matches = contactMatchesQuery(query);
        const select = form.querySelector('[data-build152-contact]');
        if (select && matches.length === 1) {
          select.value = String(matches[0].id);
          form.dataset.build153AutoContactId = String(matches[0].id);
          renderContactPreview(form);
          const address = matches[0].address || '';
          const current = location?.value.trim() || '';
          const previous = form.dataset.build153AutoContactAddress || '';
          const previousAutoLocation = form.dataset.build153AutoLocation || '';
          if (address && location && (!current || current === previous || current === previousAutoLocation)) {
            location.value = address;
            form.dataset.build153AutoContactAddress = address;
          }
        } else if (select && select.value && form.dataset.build153AutoContactId === select.value) {
          select.value = '';
          form.dataset.build153AutoContactId = '';
          renderContactPreview(form);
        }
      });
      title.addEventListener('blur', () => {
        const parsed = smartDateTime(title.value);
        if (parsed && parsed.title) title.value = parsed.title;
        const value = title.value.trim();
        if (!value) return;
        const key = value.toLowerCase().replace(/\s+/g, ' ').slice(0, 160);
        const existing = fav('event_title', key);
        const button = form.querySelector('[data-build152-fav-title]');
        if (button) {
          button.textContent = existing ? '★ Saved title' : '☆ Save title';
          button.dataset.saved = existing ? '1' : '0';
        }
      });
    }

    const location = form.elements.location;
    if (location) {
      const existingNote = form.elements.notes?.value || '';
      const contact = currentContact(contactFromNote(existingNote));
      const contactRow = document.createElement('div');
      contactRow.innerHTML = contactMarkup(contact?.id || '');
      location.insertAdjacentElement('beforebegin', contactRow.firstElementChild);
      const select = form.querySelector('[data-build152-contact]');
      renderContactPreview(form);
      if (contact?.address && !location.value.trim()) {
        location.value = contact.address;
        form.dataset.build153AutoContactAddress = contact.address;
      }
      select?.addEventListener('change', () => {
        form.dataset.build153AutoContactId = '';
        const item = contacts.find(x => String(x.id) === String(select.value));
        renderContactPreview(form);
        if (!item) return;
        const current = location.value.trim();
        const previous = form.dataset.build153AutoContactAddress || '';
        if (item.address && (!current || current === previous)) {
          location.value = item.address;
          form.dataset.build153AutoContactAddress = item.address;
        }
        const title = form.elements.title;
        if (title && (!title.value.trim() || title.value.toLowerCase().includes('appointment at'))) {
          title.value = title.value.trim() || ('Appointment at ' + item.name);
        }
      });
      if (select && !select.value) {
        const titleText = form.elements.title?.value || '';
        const match = contactMatchesQuery(titleText.replace(/^appointment\s+at\s+/i,''));
        if (match.length === 1) {
          select.value = String(match[0].id);
          renderContactPreview(form);
          if (match[0].address && !location.value.trim()) {
            location.value = match[0].address;
            form.dataset.build153AutoContactAddress = match[0].address;
          }
        }
      }

      const importPhoneButton = document.createElement('button');
      importPhoneButton.type = 'button';
      importPhoneButton.className = 'small-button';
      importPhoneButton.dataset.build152ImportContact = '1';
      importPhoneButton.textContent = '↳ Import phone contact';
      location.insertAdjacentElement('afterend', importPhoneButton);

      const saveContactButton = document.createElement('button');
      saveContactButton.type = 'button';
      saveContactButton.className = 'small-button';
      saveContactButton.dataset.build152SaveContact = '1';
      saveContactButton.textContent = '＋ Save as contact';
      location.insertAdjacentElement('afterend', saveContactButton);

      const id = 'align152-location-suggestions';
      location.setAttribute('list', id);
      const dl = document.createElement('datalist');
      dl.id = id;
      locationSuggestions().forEach(item => {
        const option = document.createElement('option');
        option.value = item.value;
        option.label = item.label;
        dl.appendChild(option);
      });
      form.appendChild(dl);

      const row = document.createElement('div');
      row.className = 'build152-favourite-row';
      row.innerHTML = '<button type="button" class="small-button" data-build152-fav-location>☆ Save location</button>' +
        '<span class="helper">Saved favourites appear as typing suggestions.</span>';
      location.insertAdjacentElement('afterend', row);

      const titleButton = document.createElement('button');
      titleButton.type = 'button';
      titleButton.className = 'small-button build152-title-favourite';
      titleButton.dataset.build152FavTitle = '1';
      titleButton.textContent = '☆ Save title';
      title.insertAdjacentElement('afterend', titleButton);
    }
  }

  function enhanceVisibleUI() {
    const form = document.querySelector('form[data-form="organiser-event"]');
    if (form) enhanceEventForm(form);

    decorateEventContacts();
    document.querySelectorAll('.organiser-section-tile').forEach(tile => {
      const key = tile.dataset.id;
      const isFav = !!fav('section', key);
      tile.classList.toggle('build152-favourite', isFav);
      if (isFav && !tile.querySelector('.build152-fav-mark')) {
        const mark = document.createElement('span');
        mark.className = 'build152-fav-mark';
        mark.setAttribute('aria-hidden','true');
        mark.textContent = '★';
        tile.appendChild(mark);
      }
    });
  }

  const observer = new MutationObserver(() => enhanceVisibleUI());
  observer.observe(document.querySelector('#app') || document.body, {childList:true, subtree:true});

  document.addEventListener('submit', event => {
    const form = event.target.closest('form[data-form="organiser-event"]');
    if (!form) return;
    const id = form.elements.align_contact_id?.value;
    const notes = form.elements.notes;
    if (!notes) return;
    const existing = String(notes.value || '').replace(/\n?\[Align contact\]\s*\{.*?\}(?:\n|$)/g,'').trim();
    const contact = contacts.find(x => String(x.id) === String(id));
    if (!contact) { notes.value = existing; return; }
    const marker = '[Align contact] ' + JSON.stringify({id:contact.id});
    notes.value = marker + (existing ? '\n' + existing : '');
  }, true);

  document.addEventListener('click', async event => {
    const manageContacts = event.target.closest('[data-build153-manage-contacts]');
    if (manageContacts) {
      openContactManager();
      return;
    }

    const importPhoneButton = event.target.closest('[data-build152-import-contact]');
    if (importPhoneButton) {
      const form = importPhoneButton.closest('form[data-form="organiser-event"]');
      if (form) await importPhoneContact(form);
      return;
    }

    const saveContactButton = event.target.closest('[data-build152-save-contact]');
    if (saveContactButton) {
      const form = saveContactButton.closest('form[data-form="organiser-event"]');
      const name = form?.elements.title?.value.trim();
      const address = form?.elements.location?.value.trim();
      if (!name) { toast('Enter a contact name in the event title first.'); return; }
      openContactManager({name, address, phone:''});
      return;
    }

    const favLocation = event.target.closest('[data-build152-fav-location]');
    if (favLocation) {
      const form = favLocation.closest('form[data-form="organiser-event"]');
      const input = form?.elements.location;
      const value = input?.value.trim();
      if (!value) { toast('Enter a location first.'); return; }
      const key = value.toLowerCase().replace(/\s+/g, ' ').slice(0, 240);
      await toggleFavourite('location', key, value, value, {source:'event-editor'});
      favLocation.textContent = fav('location', key) ? '★ Saved location' : '☆ Save location';
      return;
    }

    const favTitle = event.target.closest('[data-build152-fav-title]');
    if (favTitle) {
      const form = favTitle.closest('form[data-form="organiser-event"]');
      const value = form?.elements.title?.value.trim();
      if (!value) { toast('Enter an event title first.'); return; }
      const key = value.toLowerCase().replace(/\s+/g, ' ').slice(0, 160);
      await toggleFavourite('event_title', key, value, value, {source:'event-editor'});
      favTitle.textContent = fav('event_title', key) ? '★ Saved title' : '☆ Save title';
      return;
    }

    const sectionStar = event.target.closest('.build152-fav-mark');
    if (sectionStar) {
      event.stopPropagation();
      const tile = sectionStar.closest('.organiser-section-tile');
      if (!tile) return;
      const key = tile.dataset.id;
      const section = state.boot?.sections?.find(x => String(x.id) === String(key));
      if (!section) return;
      await toggleFavourite('section', key, section.name, section.name, {icon:section.icon});
      return;
    }

  }, true);

  function listViewSwitch() {
    return '<p class="subtle">Month agenda</p>';
  }

  function listCalendar() {
    const data = state.monthData?.month === state.scheduleMonth ? state.monthData : null;
    const label = prettyDate(state.scheduleMonth + '-01', {month:'long',year:'numeric'});
    if (!data) return '<section class="page"><div class="add-head"><p class="eyebrow">Your calendar</p><h1>Planner</h1>' +
      listViewSwitch() + '<p class="empty">Loading calendar…</p></section>';

    const [yy, mm] = state.scheduleMonth.split('-').map(Number);
    const lastDay = new Date(yy, mm, 0).getDate();
    const events = [...(data.events || []), ...(data.imported_events || [])];
    const rows = Array.from({length:lastDay}, (_, n) => state.scheduleMonth + '-' + String(n + 1).padStart(2, '0')).map(date => {
      const dayEvents = events.filter(event => String(event.start_at || '').slice(0, 10) === date)
        .sort((a, b) => String(a.start_at).localeCompare(String(b.start_at)));
      if (!dayEvents.length) return '';
      const cards = dayEvents.map(event => {
        const time = event.all_day ? 'All day' : escapeHtml(String(event.start_at || '').slice(11, 16));
        const location = event.location ? '<small>' + escapeHtml(event.location) + '</small>' : '';
        return '<article class="card week-event-row"><span class="week-event-time">' + time +
          '</span><span><strong>' + escapeHtml(event.title || 'Event') + '</strong>' + location + '</span></article>';
      }).join('');
      return '<section class="schedule-day build152-list-day' + (date === isoToday() ? ' is-today' : '') + '"><h2>' +
        escapeHtml(prettyDate(date)) + (date === isoToday() ? ' · Today' : '') + '</h2>' + cards + '</section>';
    }).join('');

    return '<section class="page"><div class="add-head"><p class="eyebrow">Your calendar</p><h1>Planner</h1>' +
      '<p class="subtle">Section and imported calendar events in date order.</p>' +
      listViewSwitch() +
      '<div class="schedule-week-nav"><button class="secondary-button" data-build152-list-nav="-1">‹</button>' +
      '<h2>' + escapeHtml(label) + '</h2><button class="secondary-button" data-build152-list-nav="1">›</button></div>' +
      '<div class="button-row"><button class="small-button" data-build152-list-today>Current month</button></div>' +
      '<div class="build152-list-compact">' + (rows || '<div class="card empty">Nothing planned this month.</div>') + '</div></section>';
  }

  window.renderCalendar = function build152RenderCalendar() {
    state.scheduleView = 'list';
    return listCalendar();
  };

  document.addEventListener('click', event => {
    const nav = event.target.closest('[data-build152-list-nav]');
    if (nav) {
      event.preventDefault();
      event.stopImmediatePropagation();
      const offset = Number(nav.dataset.build152ListNav);
      const current = fromIso(state.scheduleMonth + '-01');
      current.setMonth(current.getMonth() + offset);
      void loadScheduleMonth(toIso(current).slice(0,7));
      return;
    }
    const today = event.target.closest('[data-build152-list-today]');
    if (today) {
      event.preventDefault();
      event.stopImmediatePropagation();
      void loadScheduleMonth(isoToday().slice(0,7));
    }
  }, true);

  A.contactsReady = loadContacts();
  window.addEventListener('load', () => { setTimeout(loadFavourites, 0); });
  setTimeout(loadFavourites, 0);
})();
