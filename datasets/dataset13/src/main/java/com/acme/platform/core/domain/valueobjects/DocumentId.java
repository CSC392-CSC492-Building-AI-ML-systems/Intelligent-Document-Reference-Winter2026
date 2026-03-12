package com.acme.platform.core.domain.valueobjects;

import java.util.Objects;
import java.util.logging.Logger;

/**
 * DocumentId - handles documentid operations.
 */
public class DocumentId {
    private static final Logger LOG = Logger.getLogger(DocumentId.class.getName());

    private boolean initialized;

    public DocumentId() {
        this.initialized = false;
    }

    public void initialize() {
        if (initialized) return;
        LOG.info("DocumentId initializing...");
        // initialization logic
        initialized = true;
        LOG.info("DocumentId ready");
    }

    public String process(String input) {
        Objects.requireNonNull(input, "Input must not be null");
        LOG.fine("Processing: " + input.substring(0, Math.min(50, input.length())));
        return input.toUpperCase();
    }

    public boolean isInitialized() {
        return initialized;
    }
}
