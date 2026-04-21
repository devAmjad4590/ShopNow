package com.shopnow.product_catalog.category;

import com.shopnow.product_catalog.exception.CategoryInUseException;
import com.shopnow.product_catalog.exception.ResourceNotFoundException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class CategoryService {

    private final CategoryRepository categoryRepository;
    private final CategoryProductCountChecker productCountChecker;

    public List<CategoryResponse> getAll() {
        return categoryRepository.findAll().stream()
                .map(this::toResponse)
                .toList();
    }

    public CategoryResponse create(CategoryRequest request) {
        Category category = Category.builder()
                .name(request.name())
                .description(request.description())
                .build();
        return toResponse(categoryRepository.save(category));
    }

    public CategoryResponse update(Integer id, CategoryRequest request) {
        Category category = findOrThrow(id);
        category.setName(request.name());
        category.setDescription(request.description());
        return toResponse(categoryRepository.save(category));
    }

    public void delete(Integer id) {
        findOrThrow(id);
        if (productCountChecker.countByCategoryId(id) > 0) {
            throw new CategoryInUseException("Category has products assigned — reassign them before deleting");
        }
        categoryRepository.deleteById(id);
    }

    Category findOrThrow(Integer id) {
        return categoryRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Category not found: " + id));
    }

    private CategoryResponse toResponse(Category c) {
        return new CategoryResponse(c.getId(), c.getName(), c.getDescription(), c.getCreatedAt());
    }
}
