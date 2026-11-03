// JavaScript source code
(() => {
  const body = document.body;

  const sidebar = document.querySelector('#builder-sidebar');
  const backdrop = document.querySelector('#builder-sidebar-backdrop');

  const openButton = document.querySelector('#builder-nav-toggle');
  const closeButton = document.querySelector('#builder-nav-close');

  const previewButton = document.querySelector('#preview-toggle');


  function openNavigation() {
    body.classList.add('builder-nav-open');

    if(backdrop) {
      backdrop.hidden = false;
    }

    if(openButton) {
      openButton.setAttribute(
        'aria-expanded',
        'true'
      );
    }
  }


  function closeNavigation() {
    body.classList.remove('builder-nav-open');

    if(backdrop) {
      backdrop.hidden = true;
    }

    if(openButton) {
      openButton.setAttribute(
        'aria-expanded',
        'false'
      );
    }
  }


  openButton?.addEventListener(
    'click',
    openNavigation
  );


  closeButton?.addEventListener(
    'click',
    closeNavigation
  );


  backdrop?.addEventListener(
    'click',
    closeNavigation
  );


  document.addEventListener(
    'keydown',
    event => {
      if(event.key === 'Escape') {
        closeNavigation();
      }
    }
  );


  document.addEventListener(
    'click',
    event => {
      const tab = event.target.closest(
        '[data-tab]'
      );

      if(
        tab &&
        window.matchMedia(
          '(max-width: 900px)'
        ).matches
      ) {
        closeNavigation();
      }
    }
  );


  function updatePreviewButton() {
    if(!previewButton) {
      return;
    }

    const hidden = body.classList.contains(
      'preview-hidden'
    );

    previewButton.textContent =
      hidden
        ? 'Show preview'
        : 'Hide preview';

    previewButton.setAttribute(
      'aria-pressed',
      String(hidden)
    );
  }


  previewButton?.addEventListener(
    'click',
    () => {
      body.classList.toggle(
        'preview-hidden'
      );

      updatePreviewButton();
    }
  );


  updatePreviewButton();


  /*
   * Make the heading follow the section the
   * user is currently editing.
   */

  const pageTitle =
    document.querySelector(
      '#builder-page-title'
    );


  const titles = {
    overview: 'Edit your app',
    startup: 'Startup',
    menus: 'Menus',
    'home-nav': 'Home & navigation',
    'base-structure': 'Base structure',
    layouts: 'Databases',
    'travel-results': 'Travel',
    review: 'Review changes'
  };


  function updatePageTitle(tab) {
    if(!pageTitle) {
      return;
    }

    pageTitle.textContent =
      titles[tab] ||
      'Edit your app';
  }


  document.addEventListener(
    'click',
    event => {
      const button =
        event.target.closest(
          '[data-tab]'
        );

      if(!button) {
        return;
      }

      updatePageTitle(
        button.dataset.tab
      );
    }
  );


  /*
   * Search jumps back to Overview in the
   * existing Owner Builder code.
   *
   * Keep the visible heading in sync.
   */

  const search =
    document.querySelector(
      '#edit-search'
    );


  search?.addEventListener(
    'input',
    () => {
      updatePageTitle(
        'overview'
      );
    }
  );


  /*
   * When switching to phone preview,
   * leave the actual Builder controls usable.
   */

  const previewSize =
    document.querySelector(
      '#preview-size'
    );


  previewSize?.addEventListener(
    'change',
    () => {
      if(
        previewSize.value === 'phone' &&
        window.innerWidth < 700
      ) {
        body.classList.remove(
          'preview-hidden'
        );

        updatePreviewButton();
      }
    }
  );


  /*
   * If the screen becomes desktop-sized,
   * make sure the mobile drawer is closed.
   */

  window.addEventListener(
    'resize',
    () => {
      if(window.innerWidth > 900) {
        closeNavigation();
      }
    }
  );


  /*
   * Initial accessibility state.
   */

  if(sidebar) {
    sidebar.setAttribute(
      'aria-label',
      'Align Builder navigation'
    );
  }
})();