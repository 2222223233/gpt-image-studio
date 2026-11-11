// Reference files stay in browser memory until the user submits a request.
(() => {
  const MAX_FILE = 20 * 1024 * 1024;
  const MAX_TOTAL = 40 * 1024 * 1024;
  let refs = [], processing = false, locked = false;
  const input = document.getElementById('reference-input');
  const zone = document.getElementById('upload-zone');
  const list = document.getElementById('reference-list');
  const hint = document.getElementById('reference-status');
  const choose = document.getElementById('choose-reference');
  const clear = document.getElementById('clear-references');
  const message = (text, error = false) => {hint.textContent = text; hint.classList.toggle('warn', error);};
  function updateButtons() {
    const disabled = processing || locked;
    choose.disabled = input.disabled = disabled;
    clear.disabled = disabled || !refs.length;
    document.getElementById('generate').disabled = disabled;
    document.getElementById('preview').disabled = disabled;
    document.querySelectorAll('.remove-reference,.reuse-reference').forEach(button => button.disabled = disabled);
  }
  function render() {
    list.replaceChildren();
    refs.forEach((ref, index) => {
      const tile = document.createElement('div'); tile.className = 'reference-tile';
      const img = document.createElement('img'); img.src = ref.url; img.alt = '图' + (index + 1) + '：' + ref.file.name;
      const caption = document.createElement('div'); caption.textContent = '图' + (index + 1) + ' · ' + ref.width + ' × ' + ref.height; caption.className = 'reference-caption';
      const name = document.createElement('div'); name.className = 'reference-name'; name.textContent = ref.file.name; name.title = ref.file.name;
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'remove-reference'; remove.textContent = '×'; remove.setAttribute('aria-label', '移除图' + (index + 1));
      remove.onclick = () => {if (locked || processing) return; URL.revokeObjectURL(ref.url); refs.splice(index, 1); render();};
      tile.append(img, caption, name, remove); list.append(tile);
    });
    document.getElementById('mode-badge').textContent = refs.length ? '图片参考 / 修改 · ' + refs.length + ' 张' : '文字生成';
    if (!locked) document.getElementById('generate-label').textContent = refs.length ? '按图片生成 / 修改' : '生成图片';
    message(refs.length ? '已选 ' + refs.length + ' 张 · ' + (refs.reduce((n, r) => n + r.file.size, 0) / 1024 / 1024).toFixed(2) + ' MB。可在描述中引用“图1”“图2”。' : '支持 PNG / JPEG / WebP；最多 16 张，单张 20 MB，合计 40 MB。');
    updateButtons();
  }
  async function addFiles(files) {
    if (processing || locked) return;
    processing = true; updateButtons();
    const errors = [];
    try {
      for (const file of files) {
        if (refs.length >= 16) {errors.push('最多可选择 16 张图片。'); break;}
        if (!file.size || file.size > MAX_FILE) {errors.push(file.name + '：文件为空或超过 20 MB。'); continue;}
        if (refs.reduce((n, r) => n + r.file.size, 0) + file.size > MAX_TOTAL) {errors.push(file.name + '：图片总大小不能超过 40 MB。'); continue;}
        if (!/\.(png|jpe?g|webp)$/i.test(file.name) && !['image/png','image/jpeg','image/webp'].includes(file.type)) {errors.push(file.name + '：请选择 PNG、JPEG 或 WebP。'); continue;}
        const url = URL.createObjectURL(file);
        try {
          const image = new Image();
          image.src = url; await image.decode();
          const width = image.naturalWidth, height = image.naturalHeight;
          if (!width || !height || width * height > 16777216) throw new Error('图片尺寸无效或超过 16,777,216 像素。');
          refs.push({file, url, width, height});
        } catch (error) {URL.revokeObjectURL(url); errors.push(file.name + '：无法读取图片，或尺寸过大。');}
      }
    } finally {
      processing = false; input.value = ''; render();
      if (errors.length) message(errors.join('\n'), true);
    }
  }
  choose.onclick = () => input.click();
  input.onchange = () => addFiles(Array.from(input.files));
  clear.onclick = () => {if (processing || locked) return; refs.forEach(ref => URL.revokeObjectURL(ref.url)); refs = []; render();};
  zone.ondragover = event => {event.preventDefault(); if (!locked && !processing) zone.classList.add('dragging');};
  zone.ondragleave = () => zone.classList.remove('dragging');
  zone.ondrop = event => {event.preventDefault(); zone.classList.remove('dragging'); addFiles(Array.from(event.dataTransfer.files));};
  function encode(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve({b64_json: String(reader.result).split(',')[1]});
      reader.onerror = () => reject(new Error('读取参考图片失败，请重新选择。'));
      reader.onabort = () => reject(new Error('读取参考图片被中止，请重新选择。'));
      reader.readAsDataURL(file);
    });
  }
  window.referenceUploads = {
    async serialize() {
      if (processing) throw new Error('图片仍在读取，请稍候。');
      const result = [];
      for (const ref of refs) result.push(await encode(ref.file));
      return result;
    },
    setBusy(value) {locked = value; updateButtons(); if (!value) render();},
    async useResult(item) {
      if (locked || processing) return;
      try {
        const response = await fetch(item.url);
        if (!response.ok) throw new Error('无法读取结果图片。');
        const blob = await response.blob();
        await addFiles([new File([blob], item.name, {type: blob.type})]);
      } catch (error) {message(error.message, true);}
    }
  };
  render();
})();
