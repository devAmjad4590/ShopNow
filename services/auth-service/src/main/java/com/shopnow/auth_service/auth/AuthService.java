package com.shopnow.auth_service.auth;

import com.shopnow.auth_service.user.Role;
import com.shopnow.auth_service.user.User;
import com.shopnow.auth_service.user.UserRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class AuthService {
    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    public RegistrationResponse registerUser(RegistrationRequest req){
        User newUser = User.builder()
                .firstName(req.getFirstName())
                .lastName(req.getLastName())
                .email(req.getEmail())
                .password(passwordEncoder.encode(req.getPassword()))
                .role(Role.USER)
                .build();
        userRepository.save(newUser);

        return RegistrationResponse.builder()
                .message("User has been created successfully!")
                .build();
    }
}
