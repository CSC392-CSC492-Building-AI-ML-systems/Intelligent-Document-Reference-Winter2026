package com.acme.platform.core.domain.entities;

import java.util.Objects;
import java.util.logging.Logger;

/**
 * Document - handles document operations.
 */
public class Document {
    private static final Logger LOG = Logger.getLogger(Document.class.getName());

    private boolean initialized;

    public Document() {
        this.initialized = false;
    }

    public void initialize() {
        if (initialized) return;
        LOG.info("Document initializing...");
        // initialization logic
        initialized = true;
        LOG.info("Document ready");
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
