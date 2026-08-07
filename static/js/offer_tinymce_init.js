// Initialize TinyMCE for offer editor fields with robust variable insertion and fallback.
(function () {
  function initEditor(selector) {
    if (!window.tinymce || !document.querySelector(selector)) return;
    tinymce.init({
      selector: selector,
      menubar: false,
      plugins: ['image', 'table', 'lists', 'link', 'code', 'advlist', 'fullscreen'],
      toolbar: 'undo redo | bold italic underline strikethrough | fontfamily fontsize | alignleft aligncenter alignright justify | bullist numlist | table | link image | code fullscreen',
      images_upload_url: '/api/offers/uploads/image/',
      images_upload_credentials: true,
      automatic_uploads: true,
      paste_data_images: true,
      height: 420,
      resize: true,
      relative_urls: false,
      remove_script_host: false,
      convert_urls: true,
      font_size_formats: '8pt 10pt 12pt 14pt 18pt 24pt 30pt 36pt',
      font_formats: 'Arial=arial,helvetica,sans-serif; Courier New=courier new,courier,monospace; Georgia=georgia,serif; Helvetica=helvetica,arial,sans-serif; Times New Roman=times new roman,times,serif; Trebuchet MS=trebuchet ms,sans-serif; Verdana=verdana,arial,sans-serif',
      content_style: 'body { font-family: Arial, Helvetica, sans-serif; font-size:14px; line-height:1.6; padding: 12px; } img { max-width: 100%; height: auto; } table { border-collapse: collapse; width: 100%; } td, th { border: 1px solid #d1d5db; padding: 8px; }',
      setup: function (editor) {
        editor.on('change keyup input ExecCommand nodeChange', function () {
          editor.save();
        });
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initEditor('textarea.rich-editor');
    initEditor('#id_html_content');
    initEditor('#id_html_body_template');
  });

  // Global helper to insert variables into TinyMCE or targeted input elements
  window.insertOfferVariable = function (varName, targetId) {
    var tag = '{{' + varName + '}}';

    // 1. Try TinyMCE editor instance by target ID first
    if (targetId && window.tinymce) {
      var editor = tinymce.get(targetId);
      if (editor && !editor.isHidden()) {
        editor.focus();
        editor.execCommand('mceInsertContent', false, tag);
        editor.save();
        return;
      }
    }

    // 2. Try active TinyMCE editor
    if (window.tinymce && tinymce.activeEditor && !tinymce.activeEditor.isHidden()) {
      tinymce.activeEditor.focus();
      tinymce.activeEditor.execCommand('mceInsertContent', false, tag);
      tinymce.activeEditor.save();
      return;
    }

    // 3. Target element is a standard input or un-initialized textarea
    if (targetId) {
      var targetEl = document.getElementById(targetId);
      if (targetEl) {
        if (targetEl.tagName === 'INPUT' || targetEl.tagName === 'TEXTAREA') {
          var start = targetEl.selectionStart !== undefined ? targetEl.selectionStart : targetEl.value.length;
          var end = targetEl.selectionEnd !== undefined ? targetEl.selectionEnd : targetEl.value.length;
          var val = targetEl.value || '';
          targetEl.value = val.substring(0, start) + tag + val.substring(end);
          targetEl.focus();
          try {
            targetEl.setSelectionRange(start + tag.length, start + tag.length);
          } catch (e) {}
          return;
        }
      }
    }
  };
})();
