package com.acme.platform.core.domain.valueobjects;

import java.util.Objects;
import java.util.logging.Logger;

/**
 * Score - handles score operations.
 */
public class Score {
    private static final Logger LOG = Logger.getLogger(Score.class.getName());

    private boolean initialized;

    public Score() {
        this.initialized = false;
    }

    public void initialize() {
        if (initialized) return;
        LOG.info("Score initializing...");
        // initialization logic
        initialized = true;
        LOG.info("Score ready");
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
