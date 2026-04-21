package com.shopnow.product_catalog.category;

import com.shopnow.product_catalog.config.AuthRole;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

@RestController
@RequestMapping("/categories")
@RequiredArgsConstructor
public class CategoryController {

    private final CategoryService categoryService;

    @GetMapping
    public ResponseEntity<List<CategoryResponse>> getAll() {
        return ResponseEntity.ok(categoryService.getAll());
    }

    @PostMapping
    public ResponseEntity<CategoryResponse> create(@AuthRole String role,
                                                   @Valid @RequestBody CategoryRequest request) {
        requireAdmin(role);
        return ResponseEntity.status(HttpStatus.CREATED).body(categoryService.create(request));
    }

    @PutMapping("/{id}")
    public ResponseEntity<CategoryResponse> update(@AuthRole String role,
                                                   @PathVariable Integer id,
                                                   @Valid @RequestBody CategoryRequest request) {
        requireAdmin(role);
        return ResponseEntity.ok(categoryService.update(id, request));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@AuthRole String role, @PathVariable Integer id) {
        requireAdmin(role);
        categoryService.delete(id);
        return ResponseEntity.noContent().build();
    }

    private void requireAdmin(String role) {
        if (!"ADMIN".equals(role)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Admin access required");
        }
    }
}
