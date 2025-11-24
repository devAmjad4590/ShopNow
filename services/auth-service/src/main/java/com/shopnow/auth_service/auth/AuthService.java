package com.shopnow.auth_service.auth;

import com.shopnow.auth_service.jwt.JWTService;
import com.shopnow.auth_service.user.Role;
import com.shopnow.auth_service.user.User;
import com.shopnow.auth_service.user.UserRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class AuthService {
    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final AuthenticationManager authManager;
    private final JWTService jwtService;

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

    public LoginResponse loginUser(LoginRequest req){
        authManager.authenticate(
                new UsernamePasswordAuthenticationToken(req.getEmail(), req.getPassword())
        );
        User user = userRepository.findByEmail(req.getEmail())
                .orElseThrow(() -> new UsernameNotFoundException("This user does not exist"));
       var jwtToken = jwtService.generateToken(user);

        return LoginResponse.builder()
                .message("User is logged in!")
                .token(jwtToken)
                .build();
    }
}
