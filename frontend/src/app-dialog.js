export const createAppDialog = elements => {
  let queue = Promise.resolve();

  const open = ({
    type,
    title,
    message,
    defaultValue = "",
    confirmLabel = "OK",
    cancelLabel = "キャンセル",
    danger = false,
    inputType = "text",
    readOnly = false,
  }) => new Promise(resolve => {
    const previouslyFocused = document.activeElement;
    elements.title.textContent = title;
    elements.message.textContent = message || "";
    elements.message.hidden = !message;
    const hasInput = type === "prompt" || type === "reveal";
    elements.inputWrap.hidden = !hasInput;
    elements.input.type = inputType;
    elements.input.readOnly = readOnly;
    elements.input.value = defaultValue;
    elements.cancel.hidden = type === "alert" || type === "reveal";
    elements.cancel.textContent = cancelLabel;
    elements.confirm.textContent = confirmLabel;
    elements.confirm.classList.toggle("danger", danger);
    elements.close.onclick = () => elements.dialog.close("cancel");
    elements.cancel.onclick = () => elements.dialog.close("cancel");

    const finish = () => {
      const accepted = elements.dialog.returnValue === "confirm";
      elements.dialog.removeEventListener("close", finish);
      elements.dialog.removeEventListener("cancel", handleCancel);
      previouslyFocused?.focus?.();
      elements.input.type = "text";
      elements.input.readOnly = false;
      if (type === "prompt") resolve(accepted ? elements.input.value : null);
      else resolve(type === "alert" ? undefined : accepted);
    };
    const handleCancel = event => {
      event.preventDefault();
      elements.dialog.close("cancel");
    };

    elements.dialog.addEventListener("close", finish);
    elements.dialog.addEventListener("cancel", handleCancel);
    elements.dialog.returnValue = "cancel";
    elements.dialog.showModal();
    requestAnimationFrame(() => {
      if (hasInput) {
        elements.input.focus();
        elements.input.select();
      } else {
        elements.confirm.focus();
      }
    });
  });

  const enqueue = options => {
    const result = queue.then(() => open(options), () => open(options));
    queue = result.catch(() => {});
    return result;
  };

  return {
    alert: (message, options = {}) => enqueue({
      type: "alert",
      title: options.title || "お知らせ",
      message,
      confirmLabel: options.confirmLabel || "OK",
    }),
    confirm: (message, options = {}) => enqueue({
      type: "confirm",
      title: options.title || "確認",
      message,
      confirmLabel: options.confirmLabel || "OK",
      cancelLabel: options.cancelLabel || "キャンセル",
      danger: options.danger || false,
    }),
    prompt: (message, defaultValue = "", options = {}) => enqueue({
      type: "prompt",
      title: options.title || "入力",
      message,
      defaultValue,
      confirmLabel: options.confirmLabel || "保存",
      cancelLabel: options.cancelLabel || "キャンセル",
      inputType: options.inputType || "text",
      readOnly: options.readOnly || false,
    }),
    reveal: (message, value, options = {}) => enqueue({
      type: "reveal",
      title: options.title || "確認",
      message,
      defaultValue: value,
      confirmLabel: options.confirmLabel || "閉じる",
      inputType: "text",
      readOnly: true,
    }),
  };
};
