// Moving through the result grid with the keyboard. Nothing is worked out here: every value
// goes to the server as it is typed, and the flag, the colour and the calculated rows come
// back from it.
(function () {
  "use strict";

  var CELLS = "[data-result-grid] input[name=value], [data-result-grid] select[name=value]";

  function cells() {
    return Array.from(document.querySelectorAll(CELLS));
  }

  // Leaving a cell saves it (the change event), so moving on is all Enter has to do.
  function move(from, step) {
    var all = cells();
    var next = all[all.indexOf(from) + step];
    if (!next) {
      from.blur();
      return;
    }
    next.focus();
    if (next.select) next.select();
  }

  function saved(cell) {
    if (cell.tagName !== "SELECT") return cell.defaultValue;
    var option = Array.from(cell.options).find(function (o) {
      return o.defaultSelected;
    });
    return option ? option.value : "";
  }

  document.addEventListener(
    "keydown",
    function (event) {
      var cell = event.target;
      if (!cell || !cell.matches || !cell.matches(CELLS)) return;
      if (event.key === "Enter") {
        event.preventDefault();
        move(cell, event.shiftKey ? -1 : 1);
      } else if (event.key === "Escape") {
        // Back to what is saved; nothing is sent.
        event.preventDefault();
        cell.value = saved(cell);
      }
    },
    true
  );

  // A value the server refused comes back in its box with the reason: go back to it,
  // unless another cell is being typed in and has its own unsaved text.
  document.addEventListener("htmx:after:swap", function () {
    var refused = document.querySelector(
      "[data-result-grid] [aria-invalid=true]:not([data-seen])"
    );
    if (!refused) return;
    refused.setAttribute("data-seen", "");
    var busy = document.activeElement;
    if (busy && busy.matches && busy.matches(CELLS) && busy.value !== saved(busy)) return;
    refused.focus();
    if (refused.select) refused.select();
  });
})();
