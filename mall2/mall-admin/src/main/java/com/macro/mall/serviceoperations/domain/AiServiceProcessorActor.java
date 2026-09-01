package com.macro.mall.serviceoperations.domain;

import java.util.ArrayList;
import java.util.List;

/** Minimal identity projection for the dedicated human service-case role. */
public class AiServiceProcessorActor {
    private String username;
    private List<String> capabilities = new ArrayList<>();

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public List<String> getCapabilities() { return capabilities; }
    public void setCapabilities(List<String> capabilities) { this.capabilities = capabilities; }
}
