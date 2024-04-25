# frozen_string_literal: true

source 'http://rubygems.org'

gemspec

# Local gems are useful when developing and integrating the various dependencies.
# To favor the use of local gems, set the following environment variable:
#   Mac: export FAVOR_LOCAL_GEMS=1
#   Windows: set FAVOR_LOCAL_GEMS=1
# Note that if allow_local is true, but the gem is not found locally, then it will
# checkout the latest version (develop) from github.
allow_local = ENV['FAVOR_LOCAL_GEMS']

# Delete when these branchesa are merged and released
gem 'openstudio-extension', github: 'NREL/OpenStudio-extension-gem', branch: 'wenyi-fix-build-temp'
gem 'openstudio-standards', github: 'NREL/openstudio-standards', tag: 'v0.6.0.rc2'


# uncomment when you want CI to use develop branch of extension gem
# gem 'openstudio-extension', github: 'NREL/OpenStudio-extension-gem', branch: 'develop'

# uncomment when you want CI to use develop branch of openstudio-standards gem
# gem 'openstudio-standards', github: 'NREL/OpenStudio-standards', branch: 'master'

if allow_local && File.exist?('../OpenStudio-extension-gem')
  gem 'openstudio-extension', path: '../OpenStudio-extension-gem'
elsif allow_local
  gem 'openstudio-extension', github: 'NREL/OpenStudio-extension-gem', branch: 'develop'
end
