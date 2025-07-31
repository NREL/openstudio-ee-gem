#!/usr/bin/env ruby

require 'fileutils'

# Function to convert camelCase to snake_case
def camel_to_snake(str)
  return str if str.nil? || str.empty?

  # Handle acronyms like LCC, HVAC, EPD, etc.
  str = str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
  str = str.gsub(/([a-z\d])([A-Z])/, '\1_\2')
  str.downcase
end

# Function to fix camelCase variables in content while preserving class names
def fix_camel_case_variables(content)
  original_content = content.dup

  # Don't convert class names - look for class definitions and preserve them
  # Find class names and temporarily replace them
  class_names = []
  content.scan(/class\s+([A-Za-z0-9_]+)/) do |match|
    class_names << match[0]
  end

  # Temporarily replace class names
  temp_content = content
  class_name_map = {}
  class_names.each_with_index do |class_name, index|
    temp_name = "TEMP_CLASS_#{index}"
    class_name_map[temp_name] = class_name
    temp_content = temp_content.gsub(/#{Regexp.escape(class_name)}/, temp_name)
  end

  # Convert camelCase variables to snake_case
  temp_content = temp_content.gsub(/([a-zA-Z_][a-zA-Z0-9_]*[A-Z][a-zA-Z0-9_]*)/) do |match|
    # Skip if it's a method definition or looks like a class/module reference
    camel_to_snake(match)
  end

  # Restore class names
  final_content = temp_content
  class_name_map.each do |temp_name, original_name|
    final_content = final_content.gsub(/#{Regexp.escape(temp_name)}/, original_name)
  end

  final_content
end

# Function to process a Ruby file and fix variable naming
def fix_variable_naming(file_path)
  content = File.read(file_path)
  original_content = content.dup

  # Apply comprehensive camelCase to snake_case conversion
  content = fix_camel_case_variables(content)

  # Write file if changes were made
  if content != original_content
    File.write(file_path, content)
    puts "Fixed naming conventions in #{file_path}"
    return true
  end

  return false
end

# Function to fix nested method definitions
def fix_nested_methods(file_path)
  content = File.read(file_path)
  original_content = content.dup

  # Convert nested method definitions to lambda functions
  # Look for methods defined inside the run method
  content = content.gsub(/(\s+)def (neat_numbers\([^)]*\)[^}]*)\n(.*?)\n\1end/m) do |match|
    indent = Regexp.last_match(1)
    method_def = Regexp.last_match(2)
    method_body = Regexp.last_match(3)
    "#{indent}neat_numbers = lambda do |#{method_def.split('(')[1].split(')')[0]}|\n#{method_body.gsub(/^/, "#{indent}  ")}\n#{indent}end"
  end

  content = content.gsub(/(\s+)def (unit_helper\([^)]*\)[^}]*)\n(.*?)\n\1end/m) do |match|
    indent = Regexp.last_match(1)
    method_def = Regexp.last_match(2)
    method_body = Regexp.last_match(3)
    "#{indent}unit_helper = lambda do |#{method_def.split('(')[1].split(')')[0]}|\n#{method_body.gsub(/^/, "#{indent}  ")}\n#{indent}end"
  end

  content = content.gsub(/(\s+)def (get_total_costs_for_objects\([^)]*\)[^}]*)\n(.*?)\n\1end/m) do |match|
    indent = Regexp.last_match(1)
    method_def = Regexp.last_match(2)
    method_body = Regexp.last_match(3)
    "#{indent}get_total_costs_for_objects = lambda do |#{method_def.split('(')[1].split(')')[0]}|\n#{method_body.gsub(/^/, "#{indent}  ")}\n#{indent}end"
  end

  content = content.gsub(/(\s+)def (alter_performance\([^)]*\)[^}]*)\n(.*?)\n\1end/m) do |match|
    indent = Regexp.last_match(1)
    method_def = Regexp.last_match(2)
    method_body = Regexp.last_match(3)
    "#{indent}alter_performance = lambda do |#{method_def.split('(')[1].split(')')[0]}|\n#{method_body.gsub(/^/, "#{indent}  ")}\n#{indent}end"
  end

  # Handle reduce_schedule method specifically
  content = content.gsub(/(\s+)def (reduce_schedule\([^)]*\)[^}]*)\n(.*?)\n\1end/m) do |match|
    indent = Regexp.last_match(1)
    method_def = Regexp.last_match(2)
    method_body = Regexp.last_match(3)
    "#{indent}reduce_schedule = lambda do |#{method_def.split('(')[1].split(')')[0]}|\n#{method_body.gsub(/^/, "#{indent}  ")}\n#{indent}end"
  end

  # Write file if changes were made
  if content != original_content
    File.write(file_path, content)
    puts "Fixed nested methods in #{file_path}"
    return true
  end

  return false
end

# Function to fix operator precedence issues
def fix_operator_precedence(file_path)
  content = File.read(file_path)
  original_content = content.dup

  # Add parentheses around arithmetic operations to make precedence explicit
  # This is a simplified approach - we'll look for common patterns
  patterns = [
    [/(\w+)\.get - (\w+)\.get \* ([^,)]+)/, '\1.get - (\2.get * \3)'],
    [/(\w+)\.get \+ (\w+)\.get \* ([^,)]+)/, '\1.get + (\2.get * \3)'],
    [/(\w+) == (\w+) \|\| (\w+) == (\w+)/, '(\1 == \2) || (\3 == \4)'],
    [/(\w+) == (\w+) && (\w+) == (\w+)/, '(\1 == \2) && (\3 == \4)']
  ]

  patterns.each do |pattern, replacement|
    content = content.gsub(pattern, replacement)
  end

  # Write file if changes were made
  if content != original_content
    File.write(file_path, content)
    puts "Fixed operator precedence in #{file_path}"
    return true
  end

  return false
end

# Function to fix method names in test files
def fix_test_method_names(file_path)
  content = File.read(file_path)
  original_content = content.dup

  # Convert test method names from camelCase to snake_case
  content = content.gsub(/def (test_[A-Z][a-zA-Z0-9_]*)/) do |match|
    method_name = Regexp.last_match(1)
    "def #{camel_to_snake(method_name)}"
  end

  # Write file if changes were made
  if content != original_content
    File.write(file_path, content)
    puts "Fixed test method names in #{file_path}"
    return true
  end

  return false
end

# Function to fix class names in test files
def fix_test_class_names(file_path)
  content = File.read(file_path)
  original_content = content.dup

  # Convert test class names from CamelCase_Test to CamelCaseTest
  content = content.gsub(/class ([A-Za-z0-9_]+)_Test/) do |match|
    class_name = Regexp.last_match(1)
    "class #{class_name}Test"
  end

  # Write file if changes were made
  if content != original_content
    File.write(file_path, content)
    puts "Fixed test class names in #{file_path}"
    return true
  end

  return false
end

# Function to fix file names from CamelCase_Test.rb to snake_case_test.rb
def fix_file_names
  measure_dir = 'lib/measures'

  # Fix test file names
  Dir.glob(File.join(measure_dir, '**', '*_Test.rb')).each do |file_path|
    dir = File.dirname(file_path)
    basename = File.basename(file_path, '.rb')
    extension = '.rb'

    # Convert CamelCase_Test to snake_case_test
    new_basename = camel_to_snake(basename.sub(/_Test$/, '_test'))
    new_file_path = File.join(dir, new_basename + extension)

    if File.exist?(file_path) && !File.exist?(new_file_path)
      File.rename(file_path, new_file_path)
      puts "Renamed #{file_path} to #{new_file_path}"
    end
  end

  # Fix measure directory names
  Dir.glob(File.join(measure_dir, '*')).each do |dir_path|
    next unless File.directory?(dir_path)

    basename = File.basename(dir_path)
    new_basename = camel_to_snake(basename)

    if basename != new_basename
      new_dir_path = File.join(File.dirname(dir_path), new_basename)
      if File.exist?(dir_path) && !File.exist?(new_dir_path)
        File.rename(dir_path, new_dir_path)
        puts "Renamed directory #{dir_path} to #{new_dir_path}"
      end
    end
  end
end

# Main processing function for measure files
def process_measure_files
  measure_dir = 'lib/measures'

  Dir.glob(File.join(measure_dir, '**', 'measure.rb')).each do |file_path|
    puts "Processing #{file_path}..."

    # Fix variable naming
    fix_variable_naming(file_path)

    # Fix nested methods
    fix_nested_methods(file_path)

    # Fix operator precedence
    fix_operator_precedence(file_path)
  end

  puts 'Measure files processing complete!'
end

# Main processing function for test files
def process_test_files
  measure_dir = 'lib/measures'

  Dir.glob(File.join(measure_dir, '**', '*_test.rb')).each do |file_path|
    puts "Processing test file #{file_path}..."

    # Fix test method names
    fix_test_method_names(file_path)

    # Fix test class names
    fix_test_class_names(file_path)
  end

  puts 'Test files processing complete!'
end

# Run the processing
if __FILE__ == $0
  puts 'Starting naming convention fixes...'
  process_measure_files
  process_test_files
  fix_file_names
  puts 'All processing complete!'
end
