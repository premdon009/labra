// Keyboard shortcuts, pickers and printing for the front desk. The keys come from the
// data-shortcut attributes the server renders; no amounts are calculated here.
(function () {
  "use strict";

  function visible(el) {
    return el.getClientRects().length > 0;
  }

  // "alt+n" for Alt with a letter, "f2" for F2. AltGr reports Ctrl+Alt, so it never matches.
  function shortcutKey(event) {
    if (event.ctrlKey || event.metaKey) return null;
    if (event.code === "F2" && !event.altKey) return "f2";
    var letter = /^Key([A-Z])$/.exec(event.code || "");
    return event.altKey && letter ? "alt+" + letter[1].toLowerCase() : null;
  }

  function activate(el) {
    if (el.matches("a, button, summary")) {
      el.click();
    } else {
      el.focus();
    }
  }

  function byId(id) {
    return id ? document.getElementById(id) : null;
  }

  function flash(message) {
    var box = byId("flash");
    if (!box) return;
    box.textContent = message;
    box.hidden = !message;
  }

  document.addEventListener(
    "keydown",
    function (event) {
      var key = shortcutKey(event);
      if (key) {
        var target = Array.from(
          document.querySelectorAll('[data-shortcut="' + key + '"]')
        ).find(visible);
        if (target) {
          event.preventDefault();
          event.stopPropagation();
          activate(target);
        }
        return;
      }
      var field = event.target;
      if (!field || !field.matches || !field.matches("input, select")) return;
      if (event.key === "Enter") {
        // Enter in a box with data-enter presses that box's own button; elsewhere on a
        // counter form it does nothing, so a stray Enter never saves half a visit.
        var button = byId(field.dataset.enter);
        if (button) {
          event.preventDefault();
          button.click();
        } else if (field.closest("[data-no-enter-submit]") && field.type !== "submit") {
          event.preventDefault();
        }
      } else if (event.key === "Escape" && field.dataset.escapeClear !== undefined) {
        field.value = "";
        var shown = byId(field.dataset.escapeClear);
        if (shown) shown.replaceChildren();
      }
    },
    true
  );

  document.addEventListener("click", function (event) {
    var el = event.target.closest ? event.target : null;
    if (!el) return;
    var button = el.closest("[data-picker]");
    if (button) {
      var dialog = byId(button.dataset.picker);
      if (dialog && dialog.showModal) {
        dialog.showModal();
        var search = dialog.querySelector("[data-picker-search]");
        if (search) search.focus();
      }
      return;
    }
    var choice = el.closest("[data-pick]");
    if (choice) {
      var owner = choice.closest("dialog");
      var value = byId(owner.dataset.valueTarget);
      var label = byId(owner.dataset.labelTarget);
      if (value) value.value = choice.dataset.pick;
      if (label) label.textContent = choice.dataset.pickLabel;
      owner.close();
      var opener = document.querySelector('[data-picker="' + owner.id + '"]');
      if (opener) opener.focus();
      return;
    }
    if (el.closest("[data-close-dialog]")) {
      el.closest("dialog").close();
      return;
    }
    if (el.closest("[data-print]")) window.print();
  });

  // After the server redraws part of the screen it may name what is finished with
  // (data-done="code"): boxes marked data-clear-on for it are emptied and refocused.
  document.addEventListener("htmx:after:swap", function () {
    document.querySelectorAll("[data-done]").forEach(function (block) {
      var done = block.dataset.done;
      block.removeAttribute("data-done");
      document.querySelectorAll('[data-clear-on~="' + done + '"]').forEach(function (box) {
        if ("value" in box) {
          box.value = "";
        } else {
          box.replaceChildren();
        }
      });
      var next = document.querySelector('[data-focus-on~="' + done + '"]');
      if (next) next.focus();
    });
    var auto = document.querySelector("[data-pick-auto]");
    if (auto) {
      auto.removeAttribute("data-pick-auto");
      auto.click();
    }
  });

  document.addEventListener("htmx:before:request", function () {
    flash("");
  });
  // A 422 comes back as the same piece of screen with its messages, so it is shown as it
  // is. Other errors are not swapped in (see htmx-config in base.html) and are told here.
  document.addEventListener("htmx:response:error", function (event) {
    var ctx = event.detail && event.detail.ctx;
    var status = ctx && ctx.response ? ctx.response.status : 0;
    if (status === 422) return;
    flash(
      status === 403 || status === 404
        ? "That is not available to you. Reload the page and try again."
        : "That didn't work. Reload the page and try again."
    );
  });
  document.addEventListener("htmx:error", function () {
    flash("The server can't be reached. Check the connection and try again.");
  });

  // A print view opened with data-autoprint prints at once, then moves on.
  var page = document.body;
  if (page && page.dataset.autoprint !== undefined) {
    var next = page.dataset.afterPrint;
    if (next) {
      window.addEventListener(
        "afterprint",
        function () {
          window.location.assign(next);
        },
        { once: true }
      );
    }
    window.print();
  }
})();
