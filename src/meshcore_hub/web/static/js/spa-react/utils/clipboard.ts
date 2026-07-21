export function copyToClipboard(
  e: React.MouseEvent,
  text: string,
): void {
  e.preventDefault();
  e.stopPropagation();

  const targetElement = e.currentTarget as HTMLElement;

  const showSuccess = (target: HTMLElement) => {
    const originalText = target.textContent;
    target.textContent = "Copied!";
    target.classList.add("text-success");
    setTimeout(() => {
      target.textContent = originalText;
      target.classList.remove("text-success");
    }, 1500);
  };

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard
      .writeText(text)
      .then(() => showSuccess(targetElement))
      .catch((err) => {
        console.error("Clipboard API failed:", err);
        fallbackCopy(text, targetElement);
      });
  } else {
    fallbackCopy(text, targetElement);
  }
}

function fallbackCopy(text: string, target: HTMLElement): void {
  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.style.position = "fixed";
  textArea.style.left = "-999999px";
  textArea.style.top = "-999999px";
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();
  try {
    document.execCommand("copy");
    showSuccess(target);
  } catch (err) {
    console.error("Fallback copy failed:", err);
  }
  document.body.removeChild(textArea);
}

function showSuccess(target: HTMLElement): void {
  const originalText = target.textContent;
  target.textContent = "Copied!";
  target.classList.add("text-success");
  setTimeout(() => {
    target.textContent = originalText;
    target.classList.remove("text-success");
  }, 1500);
}
