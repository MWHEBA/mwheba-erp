/**
 * Advanced Cache Manager
 * مدير التخزين المؤقت المتقدم
 */

class CacheManager {
    constructor() {
        this.memoryCache = new Map();
        this.sessionCache = new Map();
        this.persistentCache = new Map();
        this.cacheConfig = {
            maxMemorySize: 50 * 1024 * 1024, // 50MB
            maxSessionSize: 20 * 1024 * 1024, // 20MB
            maxPersistentSize: 100 * 1024 * 1024, // 100MB
            defaultTTL: 5 * 60 * 1000, // 5 minutes
            cleanupInterval: 60 * 1000, // 1 minute
        };
        this.compressionEnabled = true;
        this.encryptionEnabled = false;
        this.storageAvailable = this.checkStorageAvailability();
        
        this.init();
    }

    checkStorageAvailability() {
        try {
            const test = '__storage_test__';
            localStorage.setItem(test, test);
            localStorage.removeItem(test);
            return true;
        } catch (e) {
            console.warn('localStorage not available, using memory cache only');
            return false;
        }
    }

    init() {
        this.loadPersistentCache();
        this.startCleanupTimer();
        this.setupStorageEventListener();
        this.setupMemoryPressureHandler();
    }

    // ========================================
    // Core Cache Operations
    // ========================================

    async set(key, data, options = {}) {
        const cacheEntry = {
            data: data,
            timestamp: Date.now(),
            ttl: options.ttl || this.cacheConfig.defaultTTL,
            size: this.calculateSize(data),
            compressed: false,
            encrypted: false,
            accessCount: 0,
            lastAccess: Date.now(),
            priority: options.priority || 'normal',
            tags: options.tags || []
        };

        // Compress large data
        if (this.compressionEnabled && cacheEntry.size > 10 * 1024) {
            try {
                cacheEntry.data = await this.compress(data);
                cacheEntry.compressed = true;
                cacheEntry.size = this.calculateSize(cacheEntry.data);
            } catch (error) {
                console.warn('Compression failed:', error);
            }
        }

        // Encrypt sensitive data
        if (this.encryptionEnabled && options.encrypt) {
            try {
                cacheEntry.data = await this.encrypt(cacheEntry.data);
                cacheEntry.encrypted = true;
            } catch (error) {
                console.warn('Encryption failed:', error);
            }
        }

        // Determine cache level
        const cacheLevel = this.determineCacheLevel(cacheEntry, options);
        
        switch (cacheLevel) {
            case 'memory':
                await this.setMemoryCache(key, cacheEntry);
                break;
            case 'session':
                await this.setSessionCache(key, cacheEntry);
                break;
            case 'persistent':
                await this.setPersistentCache(key, cacheEntry);
                break;
        }

        return true;
    }

    async get(key, options = {}) {
        let cacheEntry = null;
        let cacheLevel = null;

        // Check memory cache first
        if (this.memoryCache.has(key)) {
            cacheEntry = this.memoryCache.get(key);
            cacheLevel = 'memory';
        }
        // Check session cache
        else if (this.sessionCache.has(key)) {
            cacheEntry = this.sessionCache.get(key);
            cacheLevel = 'session';
        }
        // Check persistent cache
        else if (this.persistentCache.has(key)) {
            cacheEntry = this.persistentCache.get(key);
            cacheLevel = 'persistent';
        }

        if (!cacheEntry) {
            return null;
        }

        // Check if expired
        if (this.isExpired(cacheEntry)) {
            await this.delete(key);
            return null;
        }

        // Update access statistics
        cacheEntry.accessCount++;
        cacheEntry.lastAccess = Date.now();

        // Promote frequently accessed items to higher cache level
        if (cacheLevel !== 'memory' && cacheEntry.accessCount > 5) {
            await this.promoteToMemoryCache(key, cacheEntry);
        }

        // Decompress if needed
        let data = cacheEntry.data;
        if (cacheEntry.compressed) {
            try {
                data = await this.decompress(data);
            } catch (error) {
                console.error('Decompression failed:', error);
                await this.delete(key);
                return null;
            }
        }

        // Decrypt if needed
        if (cacheEntry.encrypted) {
            try {
                data = await this.decrypt(data);
            } catch (error) {
                console.error('Decryption failed:', error);
                await this.delete(key);
                return null;
            }
        }

        return data;
    }

    async delete(key) {
        this.memoryCache.delete(key);
        this.sessionCache.delete(key);
        this.persistentCache.delete(key);
        
        // Remove from localStorage only if available
        if (this.storageAvailable) {
            try {
                localStorage.removeItem(`cache_${key}`);
            } catch (error) {
                // Silent fail - storage not available
            }
        }

        return true;
    }

    async clear(options = {}) {
        if (options.level) {
            switch (options.level) {
                case 'memory':
                    this.memoryCache.clear();
                    break;
                case 'session':
                    this.sessionCache.clear();
                    break;
                case 'persistent':
                    this.persistentCache.clear();
                    this.clearPersistentStorage();
                    break;
            }
        } else {
            this.memoryCache.clear();
            this.sessionCache.clear();
            this.persistentCache.clear();
            this.clearPersistentStorage();
        }

        return true;
    }

    // ========================================
    // Cache Level Management
    // ========================================

    determineCacheLevel(cacheEntry, options) {
        if (options.level) {
            return options.level;
        }

        // High priority or frequently accessed -> memory
        if (cacheEntry.priority === 'high' || cacheEntry.accessCount > 10) {
            return 'memory';
        }

        // Medium size and session-specific -> session
        if (cacheEntry.size < 1024 * 1024 && options.sessionOnly) {
            return 'session';
        }

        // Large or long-term -> persistent
        return 'persistent';
    }

    async setMemoryCache(key, cacheEntry) {
        // Check memory limits
        if (this.getMemoryCacheSize() + cacheEntry.size > this.cacheConfig.maxMemorySize) {
            await this.evictMemoryCache(cacheEntry.size);
        }

        this.memoryCache.set(key, cacheEntry);
    }

    async setSessionCache(key, cacheEntry) {
        // Check session limits
        if (this.getSessionCacheSize() + cacheEntry.size > this.cacheConfig.maxSessionSize) {
            await this.evictSessionCache(cacheEntry.size);
        }

        this.sessionCache.set(key, cacheEntry);
    }

    async setPersistentCache(key, cacheEntry) {
        // Check persistent limits
        if (this.getPersistentCacheSize() + cacheEntry.size > this.cacheConfig.maxPersistentSize) {
            await this.evictPersistentCache(cacheEntry.size);
        }

        this.persistentCache.set(key, cacheEntry);
        
        // Save to localStorage only if available
        if (this.storageAvailable) {
            try {
                const serialized = JSON.stringify(cacheEntry);
                localStorage.setItem(`cache_${key}`, serialized);
            } catch (error) {
                // Silent fail - storage not available
            }
        }
    }

    async promoteToMemoryCache(key, cacheEntry) {
        // Remove from lower levels
        this.sessionCache.delete(key);
        this.persistentCache.delete(key);
        
        // Add to memory cache
        await this.setMemoryCache(key, cacheEntry);
    }

    // ========================================
    // Cache Eviction Strategies
    // ========================================

    async evictMemoryCache(requiredSize) {
        const entries = Array.from(this.memoryCache.entries());
        
        // Sort by LRU (Least Recently Used)
        entries.sort((a, b) => a[1].lastAccess - b[1].lastAccess);
        
        let freedSize = 0;
        for (const [key, entry] of entries) {
            if (freedSize >= requiredSize) break;
            
            this.memoryCache.delete(key);
            freedSize += entry.size;
        }
    }

    async evictSessionCache(requiredSize) {
        const entries = Array.from(this.sessionCache.entries());
        
        // Sort by access count and recency
        entries.sort((a, b) => {
            const scoreA = a[1].accessCount * 0.7 + (Date.now() - a[1].lastAccess) * 0.3;
            const scoreB = b[1].accessCount * 0.7 + (Date.now() - b[1].lastAccess) * 0.3;
            return scoreA - scoreB;
        });
        
        let freedSize = 0;
        for (const [key, entry] of entries) {
            if (freedSize >= requiredSize) break;
            
            this.sessionCache.delete(key);
            freedSize += entry.size;
        }
    }

    async evictPersistentCache(requiredSize) {
        const entries = Array.from(this.persistentCache.entries());
        
        // Sort by priority and age
        entries.sort((a, b) => {
            const priorityScore = { low: 1, normal: 2, high: 3 };
            const scoreA = priorityScore[a[1].priority] * 0.6 + (Date.now() - a[1].timestamp) * 0.4;
            const scoreB = priorityScore[b[1].priority] * 0.6 + (Date.now() - b[1].timestamp) * 0.4;
            return scoreA - scoreB;
        });
        
        let freedSize = 0;
        for (const [key, entry] of entries) {
            if (freedSize >= requiredSize) break;
            
            this.persistentCache.delete(key);
            if (this.storageAvailable) {
                try {
                    localStorage.removeItem(`cache_${key}`);
                } catch (error) {
                    // Silent fail
                }
            }
            freedSize += entry.size;
        }
    }

    // ========================================
    // Compression and Encryption
    // ========================================

    async compress(data) {
        if (typeof CompressionStream !== 'undefined') {
            const stream = new CompressionStream('gzip');
            const writer = stream.writable.getWriter();
            const reader = stream.readable.getReader();
            
            writer.write(new TextEncoder().encode(JSON.stringify(data)));
            writer.close();
            
            const chunks = [];
            let done = false;
            
            while (!done) {
                const { value, done: readerDone } = await reader.read();
                done = readerDone;
                if (value) chunks.push(value);
            }
            
            return new Uint8Array(chunks.reduce((acc, chunk) => [...acc, ...chunk], []));
        } else {
            // Fallback: simple string compression
            return this.simpleCompress(JSON.stringify(data));
        }
    }

    async decompress(compressedData) {
        if (typeof DecompressionStream !== 'undefined' && compressedData instanceof Uint8Array) {
            const stream = new DecompressionStream('gzip');
            const writer = stream.writable.getWriter();
            const reader = stream.readable.getReader();
            
            writer.write(compressedData);
            writer.close();
            
            const chunks = [];
            let done = false;
            
            while (!done) {
                const { value, done: readerDone } = await reader.read();
                done = readerDone;
                if (value) chunks.push(value);
            }
            
            const decompressed = new TextDecoder().decode(
                new Uint8Array(chunks.reduce((acc, chunk) => [...acc, ...chunk], []))
            );
            
            return JSON.parse(decompressed);
        } else {
            // Fallback: simple string decompression
            return JSON.parse(this.simpleDecompress(compressedData));
        }
    }

    simpleCompress(str) {
        // Simple LZ-like compression
        const dict = {};
        let data = str.split('');
        let out = [];
        let currChar;
        let phrase = data[0];
        let code = 256;
        
        for (let i = 1; i < data.length; i++) {
            currChar = data[i];
            if (dict[phrase + currChar] != null) {
                phrase += currChar;
            } else {
                out.push(phrase.length > 1 ? dict[phrase] : phrase.charCodeAt(0));
                dict[phrase + currChar] = code;
                code++;
                phrase = currChar;
            }
        }
        
        out.push(phrase.length > 1 ? dict[phrase] : phrase.charCodeAt(0));
        return out;
    }

    simpleDecompress(data) {
        // Simple LZ-like decompression
        const dict = {};
        let currChar = String.fromCharCode(data[0]);
        let oldPhrase = currChar;
        let out = [currChar];
        let code = 256;
        let phrase;
        
        for (let i = 1; i < data.length; i++) {
            let currCode = data[i];
            if (currCode < 256) {
                phrase = String.fromCharCode(data[i]);
            } else {
                phrase = dict[currCode] ? dict[currCode] : (oldPhrase + currChar);
            }
            
            out.push(phrase);
            currChar = phrase.charAt(0);
            dict[code] = oldPhrase + currChar;
            code++;
            oldPhrase = phrase;
        }
        
        return out.join('');
    }

    async encrypt(data) {
        // Simple encryption (for demo purposes)
        // In production, use Web Crypto API
        const key = 'profile-cache-key';
        const encrypted = btoa(JSON.stringify(data) + key);
        return encrypted;
    }

    async decrypt(encryptedData) {
        // Simple decryption (for demo purposes)
        const key = 'profile-cache-key';
        const decrypted = atob(encryptedData);
        return JSON.parse(decrypted.replace(key, ''));
    }

    // ========================================
    // Utility Methods
    // ========================================

    calculateSize(data) {
        if (data instanceof Uint8Array) {
            return data.length;
        }
        return new Blob([JSON.stringify(data)]).size;
    }

    isExpired(cacheEntry) {
        return Date.now() - cacheEntry.timestamp > cacheEntry.ttl;
    }

    getMemoryCacheSize() {
        let size = 0;
        for (const entry of this.memoryCache.values()) {
            size += entry.size;
        }
        return size;
    }

    getSessionCacheSize() {
        let size = 0;
        for (const entry of this.sessionCache.values()) {
            size += entry.size;
        }
        return size;
    }

    getPersistentCacheSize() {
        let size = 0;
        for (const entry of this.persistentCache.values()) {
            size += entry.size;
        }
        return size;
    }

    loadPersistentCache() {
        if (!this.storageAvailable) return;
        
        try {
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key && key.startsWith('cache_')) {
                    const cacheKey = key.replace('cache_', '');
                    const data = localStorage.getItem(key);
                    const cacheEntry = JSON.parse(data);
                    
                    // Check if expired
                    if (!this.isExpired(cacheEntry)) {
                        this.persistentCache.set(cacheKey, cacheEntry);
                    } else {
                        localStorage.removeItem(key);
                    }
                }
            }
        } catch (error) {
            // Silent fail - storage not available
        }
    }

    clearPersistentStorage() {
        if (!this.storageAvailable) return;
        
        try {
            const keysToRemove = [];
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key && key.startsWith('cache_')) {
                    keysToRemove.push(key);
                }
            }
            
            keysToRemove.forEach(key => localStorage.removeItem(key));
        } catch (error) {
            // Silent fail - storage not available
        }
    }

    startCleanupTimer() {
        setInterval(() => {
            this.cleanup();
        }, this.cacheConfig.cleanupInterval);
    }

    cleanup() {
        // Clean expired entries from all cache levels
        const now = Date.now();
        
        // Memory cache
        for (const [key, entry] of this.memoryCache.entries()) {
            if (this.isExpired(entry)) {
                this.memoryCache.delete(key);
            }
        }
        
        // Session cache
        for (const [key, entry] of this.sessionCache.entries()) {
            if (this.isExpired(entry)) {
                this.sessionCache.delete(key);
            }
        }
        
        // Persistent cache
        for (const [key, entry] of this.persistentCache.entries()) {
            if (this.isExpired(entry)) {
                this.persistentCache.delete(key);
                if (this.storageAvailable) {
                    try {
                        localStorage.removeItem(`cache_${key}`);
                    } catch (error) {
                        // Silent fail
                    }
                }
            }
        }
    }

    setupStorageEventListener() {
        window.addEventListener('storage', (event) => {
            if (event.key && event.key.startsWith('cache_')) {
                const cacheKey = event.key.replace('cache_', '');
                
                if (event.newValue) {
                    // Cache entry updated
                    try {
                        const cacheEntry = JSON.parse(event.newValue);
                        this.persistentCache.set(cacheKey, cacheEntry);
                    } catch (error) {
                        console.warn('Failed to parse cache entry:', error);
                    }
                } else {
                    // Cache entry removed
                    this.persistentCache.delete(cacheKey);
                }
            }
        });
    }

    setupMemoryPressureHandler() {
        // Handle memory pressure events
        if ('memory' in performance) {
            const checkMemoryPressure = () => {
                const memInfo = performance.memory;
                const usageRatio = memInfo.usedJSHeapSize / memInfo.jsHeapSizeLimit;
                
                if (usageRatio > 0.8) {
                    // High memory usage, clear memory cache
                    this.memoryCache.clear();
                } else if (usageRatio > 0.6) {
                    // Medium memory usage, evict some entries
                    this.evictMemoryCache(this.getMemoryCacheSize() * 0.3);
                }
            };
            
            setInterval(checkMemoryPressure, 30000); // Check every 30 seconds
        }
    }

    // ========================================
    // Public API
    // ========================================

    async getOrSet(key, factory, options = {}) {
        let data = await this.get(key, options);
        
        if (data === null) {
            data = await factory();
            await this.set(key, data, options);
        }
        
        return data;
    }

    async invalidateByTag(tag) {
        const keysToDelete = [];
        
        // Check all cache levels
        for (const [key, entry] of this.memoryCache.entries()) {
            if (entry.tags && entry.tags.includes(tag)) {
                keysToDelete.push(key);
            }
        }
        
        for (const [key, entry] of this.sessionCache.entries()) {
            if (entry.tags && entry.tags.includes(tag)) {
                keysToDelete.push(key);
            }
        }
        
        for (const [key, entry] of this.persistentCache.entries()) {
            if (entry.tags && entry.tags.includes(tag)) {
                keysToDelete.push(key);
            }
        }
        
        // Delete all tagged entries
        for (const key of keysToDelete) {
            await this.delete(key);
        }
        
        return keysToDelete.length;
    }

    getStats() {
        return {
            memory: {
                entries: this.memoryCache.size,
                size: this.getMemoryCacheSize(),
                maxSize: this.cacheConfig.maxMemorySize
            },
            session: {
                entries: this.sessionCache.size,
                size: this.getSessionCacheSize(),
                maxSize: this.cacheConfig.maxSessionSize
            },
            persistent: {
                entries: this.persistentCache.size,
                size: this.getPersistentCacheSize(),
                maxSize: this.cacheConfig.maxPersistentSize
            }
        };
    }

    async preload(keys) {
        // Preload multiple cache entries
        const promises = keys.map(key => this.get(key));
        return Promise.allSettled(promises);
    }

    destroy() {
        this.memoryCache.clear();
        this.sessionCache.clear();
        // Keep persistent cache for next session
    }
}

// Initialize cache manager
document.addEventListener('DOMContentLoaded', function() {
    if (document.querySelector('.enhanced-profile')) {
        window.cacheManager = new CacheManager();
        
        // Expose cache stats for debugging
        window.getCacheStats = () => window.cacheManager.getStats();
        window.clearCache = (level) => window.cacheManager.clear({ level });
    }
});

// Handle page unload
window.addEventListener('beforeunload', function() {
    if (window.cacheManager) {
        window.cacheManager.destroy();
    }
});

// Export for use in other modules
window.CacheManager = CacheManager;