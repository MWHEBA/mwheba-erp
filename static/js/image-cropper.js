/**
 * Image Cropper Manager
 * مدير قص الصور بنسبة 1:1 (مربع)
 */

class ImageCropperManager {
    constructor(inputId, options = {}) {
        this.inputElement = document.getElementById(inputId);
        if (!this.inputElement) {
            console.error(`Input element with id "${inputId}" not found`);
            return;
        }
        
        this.options = {
            aspectRatio: 1, // مربع فقط (1:1)
            viewMode: 1,
            dragMode: 'move',
            autoCropArea: 0.8,
            restore: false,
            guides: true,
            center: true,
            highlight: true,
            cropBoxMovable: true,
            cropBoxResizable: true,
            toggleDragModeOnDblclick: false,
            ...options
        };
        
        this.cropper = null;
        this.croppedBlob = null;
        this.originalFile = null;
        
        this.init();
    }
    
    init() {
        // إنشاء modal للـ cropper
        this.createModal();
        
        // إضافة event listener للـ input
        this.inputElement.addEventListener('change', (e) => this.handleFileSelect(e));
    }
    
    createModal() {
        // التحقق من عدم وجود modal مسبقاً
        if (document.getElementById('imageCropperModal')) {
            return;
        }
        
        const modalHTML = `
            <div id="imageCropperModal" class="image-cropper-modal">
                <div class="image-cropper-container">
                    <div class="image-cropper-header">
                        <h3>
                            <i class="fas fa-crop-alt me-2"></i>
                            قص الصورة
                        </h3>
                        <button type="button" class="image-cropper-close" id="closeCropper">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    
                    <div class="alert alert-info" style="margin-bottom: 1rem; padding: 0.75rem; border-radius: var(--border-radius); background-color: var(--info-bg, #e7f3ff); border: 1px solid var(--info-border, #b3d9ff); color: var(--info-text, #004085);">
                        <i class="fas fa-info-circle me-2"></i>
                        <small>سيتم تحسين حجم الصورة تلقائياً للحصول على أفضل جودة بأقل مساحة</small>
                    </div>
                    
                    <div class="image-cropper-body">
                        <div class="image-cropper-wrapper">
                            <img id="cropperImage" src="" alt="صورة للقص">
                        </div>
                    </div>
                    
                    <div class="image-cropper-footer">
                        <div class="cropper-controls">
                            <button type="button" class="cropper-btn cropper-btn-icon" id="zoomIn" title="تكبير">
                                <i class="fas fa-search-plus"></i>
                            </button>
                            <button type="button" class="cropper-btn cropper-btn-icon" id="zoomOut" title="تصغير">
                                <i class="fas fa-search-minus"></i>
                            </button>
                            <button type="button" class="cropper-btn cropper-btn-icon" id="rotateLeft" title="تدوير لليسار">
                                <i class="fas fa-undo"></i>
                            </button>
                            <button type="button" class="cropper-btn cropper-btn-icon" id="rotateRight" title="تدوير لليمين">
                                <i class="fas fa-redo"></i>
                            </button>
                            <button type="button" class="cropper-btn cropper-btn-icon" id="reset" title="إعادة تعيين">
                                <i class="fas fa-sync-alt"></i>
                            </button>
                        </div>
                        
                        <div>
                            <button type="button" class="cropper-btn cropper-btn-secondary" id="cancelCrop">
                                <i class="fas fa-times me-1"></i>
                                إلغاء
                            </button>
                            <button type="button" class="cropper-btn cropper-btn-primary" id="applyCrop">
                                <i class="fas fa-check me-1"></i>
                                تطبيق
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        
        // إضافة event listeners للأزرار
        this.attachModalEvents();
    }
    
    attachModalEvents() {
        const modal = document.getElementById('imageCropperModal');
        
        // زر الإغلاق
        document.getElementById('closeCropper').addEventListener('click', () => this.closeModal());
        document.getElementById('cancelCrop').addEventListener('click', () => this.closeModal());
        
        // أزرار التحكم
        document.getElementById('zoomIn').addEventListener('click', () => {
            if (this.cropper) this.cropper.zoom(0.1);
        });
        
        document.getElementById('zoomOut').addEventListener('click', () => {
            if (this.cropper) this.cropper.zoom(-0.1);
        });
        
        document.getElementById('rotateLeft').addEventListener('click', () => {
            if (this.cropper) this.cropper.rotate(-90);
        });
        
        document.getElementById('rotateRight').addEventListener('click', () => {
            if (this.cropper) this.cropper.rotate(90);
        });
        
        document.getElementById('reset').addEventListener('click', () => {
            if (this.cropper) this.cropper.reset();
        });
        
        // زر التطبيق
        document.getElementById('applyCrop').addEventListener('click', () => this.applyCrop());
        
        // إغلاق عند الضغط خارج المحتوى
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.closeModal();
            }
        });
    }
    
    handleFileSelect(event) {
        const file = event.target.files[0];
        
        if (!file) return;
        
        // التحقق من نوع الملف
        if (!file.type.match('image.*')) {
            alert('يرجى اختيار ملف صورة');
            this.inputElement.value = '';
            return;
        }
        
        // التحقق من حجم الملف (5MB max)
        if (file.size > 5 * 1024 * 1024) {
            alert('حجم الصورة يجب ألا يتجاوز 5 ميجابايت');
            this.inputElement.value = '';
            return;
        }
        
        this.originalFile = file;
        
        // قراءة الملف وعرضه في الـ cropper
        const reader = new FileReader();
        reader.onload = (e) => {
            this.showCropper(e.target.result);
        };
        reader.readAsDataURL(file);
    }
    
    showCropper(imageUrl) {
        const modal = document.getElementById('imageCropperModal');
        const image = document.getElementById('cropperImage');
        
        // تعيين الصورة
        image.src = imageUrl;
        
        // عرض الـ modal
        modal.classList.add('active');
        
        // تدمير الـ cropper القديم إن وجد
        if (this.cropper) {
            this.cropper.destroy();
        }
        
        // إنشاء cropper جديد
        this.cropper = new Cropper(image, this.options);
    }
    
    closeModal() {
        const modal = document.getElementById('imageCropperModal');
        modal.classList.remove('active');
        
        // تدمير الـ cropper
        if (this.cropper) {
            this.cropper.destroy();
            this.cropper = null;
        }
        
        // إعادة تعيين input إذا لم يتم التطبيق
        if (!this.croppedBlob) {
            this.inputElement.value = '';
        }
    }
    
    applyCrop() {
        if (!this.cropper) return;
        
        // الحصول على أبعاد الصورة الأصلية
        const imageData = this.cropper.getImageData();
        const cropBoxData = this.cropper.getCropBoxData();
        
        // تحديد الحجم الأمثل بناءً على حجم الـ crop
        // نستخدم حد أقصى 600px للصور الشخصية (كافي جداً وحجم أقل)
        let targetSize = 600;
        
        // إذا كانت الصورة المقصوصة صغيرة، نحافظ على حجمها الأصلي
        if (cropBoxData.width < targetSize) {
            targetSize = Math.round(cropBoxData.width);
        }
        
        // الحصول على الصورة المقصوصة
        this.cropper.getCroppedCanvas({
            width: targetSize,
            height: targetSize,
            imageSmoothingEnabled: true,
            imageSmoothingQuality: 'high',
            fillColor: '#fff' // خلفية بيضاء للشفافية
        }).toBlob((blob) => {
            // عرض معلومات الضغط في console
            const originalSize = this.originalFile.size;
            const compressedSize = blob.size;
            const compressionRatio = ((1 - compressedSize / originalSize) * 100).toFixed(1);
            
            
            this.croppedBlob = blob;
            
            // إنشاء File object جديد من الـ blob
            const fileName = this.originalFile.name.replace(/\.[^/.]+$/, '') + '_cropped.jpg';
            const croppedFile = new File([blob], fileName, {
                type: 'image/jpeg',
                lastModified: Date.now()
            });
            
            // تحديث الـ input بالملف الجديد
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(croppedFile);
            this.inputElement.files = dataTransfer.files;
            
            // عرض معاينة الصورة
            this.showPreview(URL.createObjectURL(blob));
            
            // إغلاق الـ modal
            this.closeModal();
            
            // إطلاق حدث مخصص مع معلومات الضغط
            this.inputElement.dispatchEvent(new CustomEvent('imageCropped', {
                detail: { 
                    file: croppedFile, 
                    blob: blob,
                    originalSize: originalSize,
                    compressedSize: compressedSize,
                    compressionRatio: compressionRatio
                }
            }));
        }, 'image/jpeg', 0.85); // جودة 85% - توازن ممتاز بين الجودة والحجم
    }
    
    showPreview(imageUrl) {
        // البحث عن container المعاينة أو إنشاؤه
        let previewContainer = this.inputElement.parentElement.querySelector('.image-preview-container');
        
        if (!previewContainer) {
            previewContainer = document.createElement('div');
            previewContainer.className = 'image-preview-container';
            this.inputElement.parentElement.appendChild(previewContainer);
        }
        
        // حساب حجم الصورة
        const sizeKB = (this.croppedBlob.size / 1024).toFixed(1);
        const sizeText = sizeKB < 1024 
            ? `${sizeKB} KB` 
            : `${(sizeKB / 1024).toFixed(2)} MB`;
        
        previewContainer.innerHTML = `
            <div class="image-preview-wrapper">
                <img src="${imageUrl}" alt="معاينة الصورة" class="image-preview">
                <div class="image-preview-actions">
                    <button type="button" class="preview-action-btn edit" title="تعديل الصورة" aria-label="تعديل الصورة">
                        <i class="fas fa-edit" aria-hidden="true"></i>
                    </button>
                    <button type="button" class="preview-action-btn delete" title="حذف الصورة" aria-label="حذف الصورة">
                        <i class="fas fa-trash-alt" aria-hidden="true"></i>
                    </button>
                </div>
            </div>
            <span class="image-preview-label">
                صورة المستخدم
                <small class="text-muted">
                    ${sizeText}
                </small>
            </span>
        `;
        
        // إضافة event listeners لأزرار المعاينة
        const editBtn = previewContainer.querySelector('.edit');
        const deleteBtn = previewContainer.querySelector('.delete');
        
        editBtn.addEventListener('click', () => {
            // إعادة فتح الـ cropper بالصورة الحالية
            if (this.croppedBlob) {
                this.showCropper(URL.createObjectURL(this.croppedBlob));
            }
        });
        
        deleteBtn.addEventListener('click', () => {
            this.clearImage();
        });
    }
    
    clearImage() {
        // مسح الـ input
        this.inputElement.value = '';
        this.croppedBlob = null;
        this.originalFile = null;
        
        // مسح المعاينة
        const previewContainer = this.inputElement.parentElement.querySelector('.image-preview-container');
        if (previewContainer) {
            previewContainer.remove();
        }
        
        // إطلاق حدث مخصص
        this.inputElement.dispatchEvent(new CustomEvent('imageCleared'));
    }
    
    // دالة للحصول على الصورة المقصوصة
    getCroppedBlob() {
        return this.croppedBlob;
    }
    
    // دالة للحصول على الملف الأصلي
    getOriginalFile() {
        return this.originalFile;
    }
}

// تصدير للاستخدام العام
window.ImageCropperManager = ImageCropperManager;
