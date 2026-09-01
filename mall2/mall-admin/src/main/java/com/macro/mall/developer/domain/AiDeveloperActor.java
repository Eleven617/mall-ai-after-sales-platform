package com.macro.mall.developer.domain;

import java.util.ArrayList;
import java.util.List;

/** Minimal identity projection for the isolated AI quality-evaluation page. */
public class AiDeveloperActor {
    private String username;
    private List<String> capabilities = new ArrayList<>();

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public List<String> getCapabilities() { return capabilities; }
    public void setCapabilities(List<String> capabilities) { this.capabilities = capabilities; }
}
