# frozen_string_literal: true

lib = File.expand_path('lib', __dir__)
$LOAD_PATH.unshift(lib) unless $LOAD_PATH.include?(lib)
require 'openstudio/ee_measures/version'

Gem::Specification.new do |spec|
  spec.name          = 'openstudio-ee'
  spec.version       = OpenStudio::EeMeasures::VERSION
  spec.authors       = ['David Goldwasser', 'Nicholas Long']
  spec.email         = ['david.goldwasser@nrel.gov', 'nicholas.long@nrel.gov']

  spec.summary       = 'Library and measures for OpenStudio for energy efficiency use cases'
  spec.description   = 'Library and measures for OpenStudio for energy efficiency use cases'
  spec.homepage      = 'https://openstudio.net'

  # Specify which files should be added to the gem when it is released.
  # The `git ls-files -z` loads the files in the RubyGem that have been added into git.
  spec.files         = Dir.chdir(File.expand_path(__dir__)) do
    `git ls-files -z`.split("\x0").reject { |f| f.match(%r{^(test|spec|features)/}) }
  end
  spec.bindir        = 'exe'
  spec.executables   = spec.files.grep(%r{^exe/}) { |f| File.basename(f) }
  spec.require_paths = ['lib']

  spec.required_ruby_version = '~> 2.5.0'

  spec.add_dependency 'bundler', '~> 2.1'

  spec.add_development_dependency 'github_api', '~> 0.18.0'
  spec.add_development_dependency 'rake', '~> 13.0'
  spec.add_development_dependency 'rspec', '~> 3.7'
  spec.add_development_dependency 'rubocop', '~> 0.54.0'

  spec.add_dependency 'openstudio-extension', '~> 0.2.1'
  spec.add_dependency 'openstudio-standards', '~> 0.2.11'

end