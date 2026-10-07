/* KCC Chess - shared page behaviour. */
(function () {
    'use strict';

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    /* Option labels look like "Name (1650)"; split them for display. */
    function parseLabel(raw) {
        var m = raw.trim().match(/^(.*)\s\((\d+)\)$/);
        return m ? { name: m[1], rating: m[2] } : { name: raw.trim(), rating: '' };
    }

    /**
     * Replace a <select> with a type-to-search input. The original select stays
     * in the form (hidden) so submission works unchanged.
     * options: placeholder, blockedValue() -> value to hide, onSelect(option)
     */
    function searchableSelect(selectEl, options) {
        options = options || {};
        var wrapper = el('div', 'search-input-wrap');
        var input = el('input', 'form-control');
        input.type = 'text';
        input.placeholder = options.placeholder || 'Search...';
        input.autocomplete = 'off';
        var menu = el('ul', 'suggestions');
        menu.hidden = true;

        selectEl.classList.add('visually-hidden-select');
        selectEl.tabIndex = -1;
        selectEl.insertAdjacentElement('afterend', wrapper);
        wrapper.appendChild(input);
        wrapper.appendChild(menu);

        var filtered = [];
        var active = -1;

        function selected() {
            return Array.prototype.find.call(selectEl.options, function (o) {
                return o.value && o.value === selectEl.value;
            }) || null;
        }

        function syncInput() {
            var opt = selected();
            input.value = opt ? parseLabel(opt.text).name : '';
        }

        function candidates(query) {
            var blocked = options.blockedValue ? options.blockedValue() : '';
            var q = (query || '').trim().toLowerCase();
            return Array.prototype.filter.call(selectEl.options, function (o) {
                if (!o.value && !options.allowEmpty) return false;
                if (blocked && o.value === blocked) return false;
                return !q || o.text.toLowerCase().indexOf(q) !== -1;
            });
        }

        function render(query) {
            filtered = candidates(query);
            active = filtered.length ? 0 : -1;
            menu.innerHTML = '';
            if (!filtered.length) {
                menu.appendChild(el('li', 'empty', 'No matching players'));
            }
            filtered.forEach(function (opt, i) {
                var parsed = parseLabel(opt.text);
                var li = el('li', i === active ? 'is-active' : '');
                li.appendChild(el('span', '', parsed.name));
                if (parsed.rating) li.appendChild(el('span', 'meta', parsed.rating));
                li.addEventListener('mousedown', function (e) {
                    e.preventDefault();
                    choose(opt);
                });
                menu.appendChild(li);
            });
            menu.hidden = false;
        }

        function highlight() {
            Array.prototype.forEach.call(menu.querySelectorAll('li'), function (li, i) {
                li.classList.toggle('is-active', i === active);
            });
        }

        function choose(opt) {
            selectEl.value = opt.value;
            syncInput();
            menu.hidden = true;
            selectEl.dispatchEvent(new Event('change', { bubbles: true }));
            if (options.onSelect) options.onSelect(opt);
        }

        input.addEventListener('focus', function () { render(''); input.select(); });
        input.addEventListener('input', function () { render(input.value); });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                if (menu.hidden) { render(input.value); return; }
                if (filtered.length) { active = Math.min(active + 1, filtered.length - 1); highlight(); }
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (filtered.length) { active = Math.max(active - 1, 0); highlight(); }
            } else if (e.key === 'Enter') {
                if (!menu.hidden && active >= 0 && filtered[active]) {
                    e.preventDefault();
                    choose(filtered[active]);
                }
            } else if (e.key === 'Escape') {
                menu.hidden = true;
                syncInput();
            }
        });
        document.addEventListener('click', function (e) {
            if (!wrapper.contains(e.target)) {
                menu.hidden = true;
                syncInput();
            }
        });

        syncInput();
        return {
            refresh: function () {
                var blocked = options.blockedValue ? options.blockedValue() : '';
                if (blocked && selectEl.value === blocked) selectEl.value = '';
                syncInput();
            }
        };
    }

    /* Live suggestions for a GET search box backed by a JSON endpoint. */
    function liveSearch(input) {
        var endpoint = input.getAttribute('data-suggest-url');
        var detailBase = input.getAttribute('data-detail-url');
        var menu = el('ul', 'suggestions');
        menu.hidden = true;
        input.parentNode.appendChild(menu);
        var timer;

        function hide() { menu.hidden = true; menu.innerHTML = ''; }

        function show(items) {
            menu.innerHTML = '';
            if (!items.length) { hide(); return; }
            items.forEach(function (item) {
                var li = el('li');
                li.appendChild(el('span', '', item.name));
                li.appendChild(el('span', 'meta', String(item.rating)));
                li.addEventListener('mousedown', function (e) {
                    e.preventDefault();
                    window.location.href = detailBase.replace('0', String(item.id));
                });
                menu.appendChild(li);
            });
            menu.hidden = false;
        }

        function fetchFor(q) {
            fetch(endpoint + '?q=' + encodeURIComponent(q), { credentials: 'same-origin' })
                .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
                .then(function (data) { show(data.results || []); })
                .catch(hide);
        }

        input.addEventListener('input', function () {
            var q = input.value.trim();
            clearTimeout(timer);
            if (!q) { hide(); return; }
            timer = setTimeout(function () { fetchFor(q); }, 180);
        });
        input.addEventListener('blur', function () { setTimeout(hide, 150); });
    }

    /* Filter a list of checkbox labels by name, and keep a selected count. */
    function pickerFilter(input) {
        var picker = document.querySelector(input.getAttribute('data-filter-target'));
        var counter = document.querySelector(input.getAttribute('data-count-target'));
        if (!picker) return;
        var labels = picker.querySelectorAll('label');

        function count() {
            if (!counter) return;
            counter.textContent = picker.querySelectorAll('input:checked').length;
        }

        input.addEventListener('input', function () {
            var q = input.value.trim().toLowerCase();
            Array.prototype.forEach.call(labels, function (label) {
                // Django wraps each checkbox label in its own <div> (or <li> in older versions).
                var parent = label.parentElement;
                var item = parent && parent !== picker && parent.children.length === 1 ? parent : label;
                item.hidden = q && label.textContent.toLowerCase().indexOf(q) === -1;
            });
        });
        picker.addEventListener('change', count);
        count();
    }

    document.addEventListener('DOMContentLoaded', function () {
        /* Rows with data-href act as links (keyboard friendly via the inner link). */
        document.querySelectorAll('tr[data-href]').forEach(function (row) {
            row.addEventListener('click', function (e) {
                if (e.target.closest('a, button, form')) return;
                window.location.href = row.getAttribute('data-href');
            });
        });

        /* Forms with data-confirm ask before submitting. */
        document.querySelectorAll('form[data-confirm]').forEach(function (form) {
            form.addEventListener('submit', function (e) {
                if (!window.confirm(form.getAttribute('data-confirm'))) e.preventDefault();
            });
        });

        /* Prevent double submits on result buttons and other POST forms. */
        document.querySelectorAll('form[method="post"]').forEach(function (form) {
            form.addEventListener('submit', function (e) {
                if (e.defaultPrevented) return;
                if (form.dataset.submitting) { e.preventDefault(); return; }
                form.dataset.submitting = '1';
            });
        });

        document.querySelectorAll('input[data-suggest-url]').forEach(liveSearch);
        document.querySelectorAll('input[data-filter-target]').forEach(pickerFilter);
    });

    /* Coming back via the browser's back button restores the page from cache; re-enable forms. */
    window.addEventListener('pageshow', function (e) {
        if (!e.persisted) return;
        document.querySelectorAll('form[data-submitting]').forEach(function (form) {
            delete form.dataset.submitting;
        });
    });

    window.KCC = { searchableSelect: searchableSelect };
})();
