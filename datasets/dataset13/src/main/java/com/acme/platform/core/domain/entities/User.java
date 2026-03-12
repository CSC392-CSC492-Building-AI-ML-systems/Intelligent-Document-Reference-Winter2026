package com.acme.platform.core.domain.entities;

import java.util.Objects;
import java.util.logging.Logger;

/**
 * User - handles user operations.
 */
public class User {
    private static final Logger LOG = Logger.getLogger(User.class.getName());

    private boolean initialized;

    public User() {
        this.initialized = false;
    }

    public void initialize() {
        if (initialized) return;
        LOG.info("User initializing...");
        // initialization logic
        initialized = true;
        LOG.info("User ready");
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
