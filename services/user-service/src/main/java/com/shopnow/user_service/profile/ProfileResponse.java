package com.shopnow.user_service.profile;

import lombok.Builder;
import lombok.Data;

import java.time.LocalDate;

@Data
@Builder
public class ProfileResponse {
    private Integer authUserId;
    private String phone;
    private LocalDate dateOfBirth;
    private String avatarUrl;
    private String bio;
}
